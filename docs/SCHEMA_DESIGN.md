# Step 7 – Normalisation & Schema Design (DataSnapshot)

This document describes the normalised schema for the VroomVroom DataSnapshot domain: **devices**, **metrics**, **snapshots**, and **snapshot_metric_values**. It explains how redundancy is eliminated and how referential integrity is enforced.

---

## 1. Entity–table mapping

| Logical entity              | Table name            | Purpose |
|----------------------------|------------------------|--------|
| **devices**                | `device`               | One row per monitored machine (host). |
| **metrics**                | `metric_type`          | Definitions of what can be measured (name + unit). |
| **snapshots**              | `snapshot`             | One row per reading event (one point-in-time capture per device). |
| **snapshot_metric_values** | `snapshot_metric`      | One row per (snapshot, metric) pair: the measured value and status. |

---

## 2. Normalisation

### 2.1 First Normal Form (1NF)

- Every table has a **primary key** (single column or composite).
- Every column holds **atomic values** (no repeating groups or lists).
- Each row is unique.

| Table             | Primary key              | Atomic columns |
|-------------------|--------------------------|----------------|
| `device`          | `id`                     | `device_id`, `label`, `first_seen` — single values. |
| `metric_type`     | `id`                     | `name`, `unit` — single values. |
| `snapshot`        | `id`                     | `device_id`, `timestamp_utc` — single values. |
| `snapshot_metric` | `(snapshot_id, metric_type_id)` | `value`, `status` — one value per (snapshot, metric). |

**Redundancy avoided:** We do *not* store metrics as repeated columns (e.g. `cpu_value`, `ram_value`, `disk_value`) or as JSON arrays in `snapshot`. Instead, each metric value is one row in `snapshot_metric`, so adding a new metric type does not require schema change.

### 2.2 Second Normal Form (2NF)

- 1NF holds.
- Every non-key attribute **depends on the whole key** (no partial dependency).

| Table             | Key                         | Non-key attributes | Why 2NF |
|-------------------|-----------------------------|--------------------|--------|
| `device`          | `id`                        | `device_id`, `label`, `first_seen` | Single-column PK → no partial dependency. |
| `metric_type`     | `id`                        | `name`, `unit`     | Single-column PK. |
| `snapshot`        | `id`                        | `device_id`, `timestamp_utc` | Single-column PK. |
| `snapshot_metric` | `(snapshot_id, metric_type_id)` | `value`, `status` | Both `value` and `status` depend on the *pair* (which snapshot, which metric), not on one part of the key alone. |

**Redundancy avoided:** Metric name/unit are not repeated in `snapshot_metric`; they live only in `metric_type`. The junction table stores only the composite key and the attributes that depend on it (`value`, `status`).

### 2.3 Third Normal Form (3NF)

- 2NF holds.
- No non-key attribute **depends on another non-key attribute** (no transitive dependency).

| Table             | Check |
|-------------------|--------|
| `device`          | `label` and `first_seen` depend only on `id` (and thus the key). No transitive dependency. |
| `metric_type`     | `unit` depends on `id` (or on `name`); we keep one row per metric type, so no transitive dependency within the table. |
| `snapshot`        | `device_id` and `timestamp_utc` depend only on `id`. |
| `snapshot_metric` | `value` and `status` depend only on the composite key. |

**Redundancy avoided:** We do *not* store device label or metric name/unit in `snapshot` or `snapshot_metric`. Those are looked up via foreign keys when needed, so each fact is stored in one place.

---

## 3. Referential integrity

### 3.1 Foreign keys and cardinality

```
device (1) ──────────── (*) snapshot
   │
   │  snapshot (*) ──── (*) metric_type
   │         │                  │
   │         └──────────────────┘
   │              snapshot_metric
   │         (snapshot_id, metric_type_id, value, status)
```

- **device → snapshot:** One device has many snapshots. `snapshot.device_id` references `device(id)`. Deleting a device should remove its snapshots → `ON DELETE CASCADE`.
- **snapshot → snapshot_metric:** One snapshot has many metric values. `snapshot_metric.snapshot_id` references `snapshot(id)`. Deleting a snapshot should remove its values → `ON DELETE CASCADE`.
- **metric_type → snapshot_metric:** One metric type appears in many snapshot_metric rows. `snapshot_metric.metric_type_id` references `metric_type(id)`. No cascade on delete: metric types are reference data; we do not delete them when cleaning snapshots.

### 3.2 Constraints

| Constraint type   | Where | Purpose |
|-------------------|--------|---------|
| **Primary key**   | All tables | Uniqueness and stable identity. |
| **Unique**        | `device.device_id`, `metric_type.name` | No duplicate device identifiers or metric names. |
| **Foreign key**   | `snapshot.device_id`, `snapshot_metric.snapshot_id`, `snapshot_metric.metric_type_id` | Only valid device and metric type references; no orphan rows. |
| **Check**         | `snapshot_metric.status IN ('normal','warning','danger')` | Domain constraint on status. |
| **NOT NULL**      | All FKs and business-critical columns | No missing references or required data. |

SQLite requires `PRAGMA foreign_keys = ON` per connection; this is set in `database.py` and in the ORM engine setup.

---

## 4. DDL (definitions)

These match the tables in `src/database.py`.

```sql
-- devices: one row per monitored machine
CREATE TABLE IF NOT EXISTS device (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id  TEXT    NOT NULL UNIQUE,
    label      TEXT    NOT NULL DEFAULT '',
    first_seen TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- metrics: definitions of what can be measured (name + unit)
CREATE TABLE IF NOT EXISTS metric_type (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE,
    unit TEXT    NOT NULL
);

-- snapshots: one row per reading event on a device
CREATE TABLE IF NOT EXISTS snapshot (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     INTEGER NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    timestamp_utc TEXT    NOT NULL
);

-- snapshot_metric_values: one value per (snapshot, metric) pair
CREATE TABLE IF NOT EXISTS snapshot_metric (
    snapshot_id    INTEGER NOT NULL REFERENCES snapshot(id)     ON DELETE CASCADE,
    metric_type_id INTEGER NOT NULL REFERENCES metric_type(id),
    value          REAL    NOT NULL,
    status         TEXT    NOT NULL CHECK (status IN ('normal', 'warning', 'danger')),
    PRIMARY KEY (snapshot_id, metric_type_id)
);
```

---

## 5. Indexes (Step 1 – indexing)

Explicit indexes are created in `src/database.py` after the tables. SQLite does **not** auto-create indexes on foreign-key columns; without them, JOINs and filters can do full table scans.

| Index | Table | Column(s) | Purpose |
|-------|--------|-----------|---------|
| `idx_snapshot_device_id` | `snapshot` | `device_id` | FK; JOIN with `device`; filter by device (e.g. list snapshots for one device). |
| `idx_snapshot_timestamp_utc` | `snapshot` | `timestamp_utc` | Frequently filtered/ordered by time; range queries. |
| `idx_snapshot_metric_snapshot_id` | `snapshot_metric` | `snapshot_id` | FK; LEFT JOIN from `snapshot` to get metrics per snapshot. |
| `idx_snapshot_metric_metric_type_id` | `snapshot_metric` | `metric_type_id` | FK; JOIN with `metric_type` for metric name/unit. |

**Already indexed:** `device.device_id` and `metric_type.name` (UNIQUE); all primary keys (id or composite). Use **EXPLAIN QUERY PLAN** and the script `scripts/verify_indexes.py` to confirm the planner uses these indexes and to compare query times.

**Step 2 – Performance (scan vs search):** Run `scripts/performance_scan_vs_search.py` to compare the same query with and without `idx_snapshot_device_id`. With the index, the planner uses a B-tree **SEARCH** (O(log n)); without it, a full table **SCAN** (O(n)). BlockTimer logs the execution time for both; the script prints the ratio and explains why index lookups scale better as the table grows.

**Step 3 – Transactions (RAII):** `TransactionManager` in `src/database.py` is a context manager: **BEGIN** on `__enter__`, **COMMIT** on normal `__exit__`, **ROLLBACK** on exception. POST /snapshots uses it so the multi-step insert (get-or-create device, insert snapshot, insert snapshot_metric rows) runs in one transaction; if any step fails, the whole change is rolled back.

**Step 5 – ORM relationships & loading:** Relationships are configured in `src/orm_models.py` (Device↔Snapshot, Snapshot↔SnapshotMetric↔MetricType) with default **lazy="select"**. **Eager loading** uses `joinedload(Snapshot.device)` and `selectinload(Snapshot.snapshot_metrics).joinedload(SnapshotMetric.metric_type)` in `orm_routes.py` to avoid N+1 queries. **Object navigation:** e.g. `snapshot.device.device_id`, `sm.metric_type.name`. Set **VROOMVROOM_SQL_ECHO=1** to log all generated SQL; run `scripts/demo_orm_loading.py` to see lazy vs eager SQL.

**Step 6 – Change tracking & session lifecycle:** Run `scripts/demo_session_lifecycle.py` to see **session.add()** (stage for insert), **session.flush()** (emit SQL, assign PKs, no COMMIT), **session.commit()**, **session.rollback()** (discard pending changes), and **session.expunge()** (detach object from session). The script inspects **session.identity_map** (all tracked instances) and **session.dirty** (modified instances), and proves that the same primary key returns the **same in-memory object** (identity map uniqueness).

---

## 6. Summary

| Goal | How it is achieved |
|------|---------------------|
| **Elimination of redundancy** | Metric definitions in one table (`metric_type`); device identity in one table (`device`). Snapshot and value tables store only IDs and values; no repeated names, units, or labels. |
| **Referential integrity** | Foreign keys from `snapshot` → `device`, and `snapshot_metric` → `snapshot` and `metric_type`. `PRAGMA foreign_keys = ON` and optional `ON DELETE CASCADE` where the lifecycle of the child depends on the parent. |
| **Extensibility** | New metric types: add a row to `metric_type` (and seed logic). New devices: add a row to `device`. No schema change needed for new metrics. |

The implementation lives in `src/database.py` (DDL and raw SQL) and `src/orm_models.py` (ORM mappings). This document is the single place for the normalisation and schema design rationale (Step 7).
