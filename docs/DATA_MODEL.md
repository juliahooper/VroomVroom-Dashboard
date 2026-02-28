# DataSnapshot Data Model – Four Layers

This document defines the DataSnapshot model at each layer: **database**, **ORM**, **server domain**, and **DTO (wire)**. Timestamps are stored and transmitted in **UTC as ISO 8601**. Identifiers are documented below (no UUIDs in current schema; typing rules if added).

---

## 1. Database model (normalized tables)

Implemented in `src/database.py`. Tables:

| Table | Columns | Notes |
|-------|---------|--------|
| **device** | `id` (PK), `device_id` (TEXT UNIQUE), `label`, `first_seen` (TEXT) | One row per machine. `first_seen` stored as ISO 8601 UTC string (e.g. from `datetime.now(timezone.utc).isoformat()` or SQLite `datetime('now')`). |
| **metric_type** | `id` (PK), `name` (UNIQUE), `unit` | Reference data: what can be measured. |
| **snapshot** | `id` (PK), `device_id` (FK → device.id), `timestamp_utc` (TEXT) | One row per reading event. **timestamp_utc**: always UTC, ISO 8601 format (e.g. `2025-02-28T14:30:00+00:00` or `2025-02-28T14:30:00.123456Z`). |
| **snapshot_metric** | `snapshot_id`, `metric_type_id` (composite PK), `value`, `status` | One row per (snapshot, metric). `status` IN ('normal','warning','danger'). |

- **Identifiers:** Integer surrogate keys (`id`) and unique business key `device_id` (string). No UUID columns in current schema.
- **Timestamps:** Stored as TEXT in UTC. Application always writes using `datetime.now(timezone.utc).isoformat()` or equivalent; readers treat values as ISO 8601 UTC.

---

## 2. ORM model (SQLAlchemy classes)

Implemented in `src/orm_models.py`. Maps 1:1 to the database tables.

| ORM class | Table | Key types |
|------------|--------|-----------|
| **Device** | device | `id: int`, `device_id: str`, `label: str`, `first_seen: str` |
| **MetricType** | metric_type | `id: int`, `name: str`, `unit: str` |
| **Snapshot** | snapshot | `id: int`, `device_id: int` (FK), `timestamp_utc: str` |
| **SnapshotMetric** | snapshot_metric | `snapshot_id: int`, `metric_type_id: int`, `value: float`, `status: str` |

- **Relationships:** Device ↔ Snapshot (one-to-many); Snapshot ↔ SnapshotMetric ↔ MetricType.
- **Timestamps:** `timestamp_utc` and `first_seen` are `Mapped[str]`; store ISO 8601 UTC strings. Application sets them with `datetime.now(timezone.utc).isoformat()`.

---

## 3. Server domain model (business logic)

Used in application code for creating snapshots, applying thresholds, and mapping to/from DB.

**In `src/datasnapshot/models.py`:**

| Type | Purpose |
|------|--------|
| **Metric** | Single measurement: `name`, `value`, `unit`, `status` (normal/warning/danger). Built from raw metrics + thresholds. |
| **Snapshot** | Point-in-time capture: `device_id: str`, **`timestamp_utc: datetime`** (timezone-aware, UTC), `metrics: list[Metric]`. Created by `create_snapshot()`; serialized to JSON for wire/TCP. |

- **Timestamp:** Domain uses `datetime` with `timezone.utc`. `create_snapshot()` sets `timestamp_utc=datetime.now(timezone.utc)`. When parsing from JSON, timestamp is normalized to UTC (naive parsed as UTC).
- **StatusSummary** | Summary of metric statuses (danger/warning/normal) for alerting.

**In `src/snapshots.py` (raw-SQL API view models):**

| Type | Purpose |
|------|--------|
| **SnapshotSummary** | List view: `id`, `device_id`, `timestamp_utc` (str), `metric_count`. |
| **SnapshotDetail** | Detail view: `id`, `device_id`, `timestamp_utc` (str), `metrics: list[MetricRecord]`. |
| **MetricRecord** | One metric in a detail: `name`, `unit`, `value`, `status`. |
| **DeviceRecord** | Device row: `id`, `device_id`, `label`, `first_seen`. |

These are built from DB rows; `timestamp_utc` and `first_seen` are ISO 8601 strings (UTC).

---

## 4. DTO model (wire JSON format)

Used over HTTP and TCP. Defined by serialization in `src/datasnapshot/models.py` (`snapshot_to_json` / `snapshot_from_json`) and by API response shapes.

**Snapshot (POST body / TCP payload):**

```json
{
  "device_id": "<string>",
  "timestamp_utc": "<ISO 8601 UTC string, e.g. 2025-02-28T14:30:00+00:00>",
  "metrics": [
    { "name": "<string>", "value": <number>, "unit": "<string>", "status": "normal|warning|danger" }
  ]
}
```

**API responses (examples):**

- **POST /snapshots** → 201: `{ "id": <int>, "device_id": "<string>", "timestamp_utc": "<ISO 8601>", "metric_count": <int> }`
- **GET /snapshots/<id>** → 200: `{ "id": <int>, "device_id": "<string>", "timestamp_utc": "<ISO 8601>", "metrics": [ { "name", "unit", "value", "status" }, ... ] }`
- **GET /devices** (raw or ORM): device objects with `id`, `device_id`, `label`, `first_seen` (ISO 8601 string).

- **Timestamps on wire:** Always ISO 8601 in UTC (e.g. with `Z` or `+00:00`). Serialization uses `datetime.isoformat()`; parsing uses `datetime.fromisoformat()` and normalizes naive datetimes to UTC.

---

## Timestamps (UTC, ISO 8601)

| Layer | Representation | Rule |
|-------|----------------|------|
| Database | TEXT | Store only UTC; format ISO 8601 (e.g. `...Z` or `...+00:00`). |
| ORM | `str` | Same as DB. Set with `datetime.now(timezone.utc).isoformat()`. |
| Domain (datasnapshot) | `datetime` | Timezone-aware, UTC. `create_snapshot()` uses `datetime.now(timezone.utc)`; JSON parse normalizes to UTC. |
| DTO (wire) | string | ISO 8601 UTC. Serialize with `.isoformat()`; require/accept UTC in APIs. |

---

## UUIDs

- **Current schema:** No UUID columns. Primary keys are integers; `device_id` is a string (e.g. hostname or config id).
- **If UUIDs are added:** Use a dedicated column (e.g. `snapshot_uuid TEXT` or `device_uuid TEXT`). In Python use `uuid.UUID`; store on wire and in DB as canonical string (e.g. `str(uuid)`). Do not use UUIDs as primary keys in SQLite without a proper type/adapter; store as TEXT and validate with `uuid.UUID(...)` in the domain layer.
