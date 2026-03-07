"""
ORM ↔ DTO mapping. Explicit conversions only; no magic.

- ORM → DTO: to_dict-style functions (snapshot_to_summary_dto, snapshot_to_detail_dto, device_to_dto).
- DTO → ORM: snapshot_from_dto(dto, session) builds Snapshot + Device + SnapshotMetrics.
- Datetime: always UTC, ISO 8601 on the wire; explicit serialize/deserialize.
- UUID: helpers for when schema has UUID columns (serialize to string, parse with uuid.UUID).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .orm_models import Device, MetricType, Snapshot, SnapshotMetric


# ---------------------------------------------------------------------------
# Datetime: explicit UTC ISO 8601
# ---------------------------------------------------------------------------

def datetime_to_iso(value: datetime | str) -> str:
    """
    Serialize datetime or already-ISO string to ISO 8601 UTC string for DTO/wire.
    ORM stores timestamp_utc as str; domain may pass datetime. No magic — explicit branch.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    raise TypeError(f"Expected datetime or str, got {type(value)}")


def iso_to_utc_datetime(value: str) -> datetime:
    """
    Parse ISO 8601 string to timezone-aware UTC datetime for domain/ORM input.
    Naive parsed values are treated as UTC.
    """
    s = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# UUID: explicit serialize/parse for when schema has UUID columns
# ---------------------------------------------------------------------------

def uuid_to_str(value: UUID | str) -> str:
    """Serialize UUID to canonical string for DTO/DB. Idempotent if already str."""
    if isinstance(value, str):
        return value
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Expected UUID or str, got {type(value)}")


def str_to_uuid(value: str) -> UUID:
    """Parse string to UUID. Raises ValueError if invalid."""
    return UUID(value)


# ---------------------------------------------------------------------------
# ORM → DTO (to_dict-style)
# ---------------------------------------------------------------------------

def snapshot_to_summary_dto(snapshot: Snapshot) -> dict[str, Any]:
    """
    Map ORM Snapshot to summary DTO (list view).
    Caller must ensure snapshot.device and snapshot.snapshot_metrics are loaded if needed.
    """
    device_id_str = snapshot.device.device_id if snapshot.device else ""
    return {
        "id": snapshot.id,
        "device_id": device_id_str,
        "device_label": snapshot.device.label if snapshot.device else "",
        "timestamp_utc": datetime_to_iso(snapshot.timestamp_utc),
        "metric_count": len(snapshot.snapshot_metrics),
    }


def snapshot_to_detail_dto(snapshot: Snapshot) -> dict[str, Any]:
    """
    Map ORM Snapshot to detail DTO (single snapshot with metrics).
    Caller must ensure snapshot.device and snapshot.snapshot_metrics + metric_type are loaded.
    """
    metrics_dto = [
        {
            "name": sm.metric_type.name,
            "unit": sm.metric_type.unit,
            "value": sm.value,
            "status": sm.status,
        }
        for sm in snapshot.snapshot_metrics
    ]
    return {
        "id": snapshot.id,
        "device_id": snapshot.device.device_id if snapshot.device else "",
        "device_label": snapshot.device.label if snapshot.device else "",
        "timestamp_utc": datetime_to_iso(snapshot.timestamp_utc),
        "metrics": metrics_dto,
    }


def device_to_dto(
    id_: int,
    device_id: str,
    label: str,
    first_seen: str,
    snapshot_count: int | None = None,
) -> dict[str, Any]:
    """
    Build device DTO from known fields (e.g. aggregate query row).
    first_seen: ISO 8601 string from DB. snapshot_count optional (from COUNT).
    """
    out: dict[str, Any] = {
        "id": id_,
        "device_id": device_id,
        "label": label,
        "first_seen": datetime_to_iso(first_seen),
    }
    if snapshot_count is not None:
        out["snapshot_count"] = snapshot_count
    return out


# ---------------------------------------------------------------------------
# Validation for upload DTO
# ---------------------------------------------------------------------------

def validate_snapshot_upload_dto(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate incoming JSON DTO for POST /upload_snapshot. Returns a normalized
    DTO dict suitable for snapshot_from_dto(), or raises ValueError with a
    clear message.
    """
    if not isinstance(data, dict):
        raise ValueError("Body must be a JSON object")

    for key in ("device_id", "timestamp_utc", "metrics"):
        if key not in data:
            raise ValueError(f"Missing required field: {key!r}")

    device_id = data["device_id"]
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Field 'device_id' must be a non-empty string")
    device_id = device_id.strip()

    timestamp_utc = data["timestamp_utc"]
    if not isinstance(timestamp_utc, str) or not timestamp_utc.strip():
        raise ValueError("Field 'timestamp_utc' must be a non-empty ISO 8601 string")
    try:
        iso_to_utc_datetime(timestamp_utc)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid 'timestamp_utc' format: {e}") from e

    metrics = data["metrics"]
    if not isinstance(metrics, list):
        raise ValueError("Field 'metrics' must be an array")

    normalized_metrics: list[dict[str, Any]] = []
    for i, m in enumerate(metrics):
        if not isinstance(m, dict):
            raise ValueError(f"metrics[{i}] must be an object")
        for key in ("name", "value", "unit", "status"):
            if key not in m:
                raise ValueError(f"metrics[{i}] missing required field: {key!r}")
        status = str(m["status"])
        if status not in ("normal", "warning", "danger"):
            raise ValueError(f"metrics[{i}].status must be one of: normal, warning, danger")
        try:
            value = float(m["value"])
        except (TypeError, ValueError):
            raise ValueError(f"metrics[{i}].value must be a number")
        normalized_metrics.append({
            "name": str(m["name"]),
            "value": value,
            "unit": str(m["unit"]),
            "status": status,
        })

    return {
        "device_id": device_id,
        "timestamp_utc": timestamp_utc.strip(),
        "metrics": normalized_metrics,
    }


# ---------------------------------------------------------------------------
# DTO → ORM (from_dict-style)
# ---------------------------------------------------------------------------

def snapshot_from_dto(dto: dict[str, Any], session: Session) -> Snapshot:
    """
    Build ORM Snapshot (and Device / SnapshotMetrics) from wire DTO.

    DTO must have: device_id (str), timestamp_utc (ISO 8601 str), metrics (list of
    { name, value, unit, status }). Creates Device if missing; looks up MetricType by name;
    skips metrics with unknown name. All conversions explicit (no magic).
    """
    device_id_str = str(dto["device_id"])
    timestamp_str = dto["timestamp_utc"]
    metrics_list = dto.get("metrics") or []

    # Explicit: parse timestamp to UTC, then store as ISO string in ORM
    dt = iso_to_utc_datetime(timestamp_str)
    timestamp_utc_stored = dt.isoformat()

    # Resolve or create Device
    device = session.scalars(
        select(Device).where(Device.device_id == device_id_str)
    ).first()
    if device is None:
        device = Device(
            device_id=device_id_str,
            label="",
            first_seen=datetime.now(timezone.utc).isoformat(),
        )
        session.add(device)
        session.flush()

    # Create Snapshot
    snapshot = Snapshot(
        device_id=device.id,
        timestamp_utc=timestamp_utc_stored,
    )
    session.add(snapshot)
    session.flush()

    # Create SnapshotMetric rows (lookup by metric name; create metric_type if missing)
    for m in metrics_list:
        if not isinstance(m, dict):
            continue
        name = m.get("name")
        if name is None:
            continue
        metric_type = session.scalars(
            select(MetricType).where(MetricType.name == name)
        ).first()
        if metric_type is None:
            # Create metric_type on-the-fly so uploads don't silently drop metrics
            unit = str(m.get("unit", ""))
            metric_type = MetricType(name=name, unit=unit)
            session.add(metric_type)
            session.flush()
        value = float(m.get("value", 0))
        status = str(m.get("status", "normal"))
        if status not in ("normal", "warning", "danger"):
            status = "normal"
        sm = SnapshotMetric(
            snapshot_id=snapshot.id,
            metric_type_id=metric_type.id,
            value=value,
            status=status,
        )
        session.add(sm)

    return snapshot


__all__ = [
    "datetime_to_iso",
    "iso_to_utc_datetime",
    "uuid_to_str",
    "str_to_uuid",
    "validate_snapshot_upload_dto",
    "snapshot_to_summary_dto",
    "snapshot_to_detail_dto",
    "device_to_dto",
    "snapshot_from_dto",
]
