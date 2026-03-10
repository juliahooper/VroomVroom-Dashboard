"""
Bridge from mobile collector output to the unified Snapshot shape.

Converts location + latest time-series point + count results into the same
Snapshot (device_id, timestamp_utc, metrics) used for PC metrics, so the rest
of CoC can consume one format for dashboards and storage.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .datasnapshot import Metric, Snapshot
from .mobile_models import CountResult, TimeSeriesPoint

# Display names must match metric_type names in the DB (same schema as PC/YouTube).
_DISPLAY: dict[str, tuple[str, str]] = {
    "risk_score": ("Cold Water Shock Risk", "%"),
    "water_temp": ("Water Temp", "°C"),
}

_COUNT_DISPLAY: dict[str, tuple[str, str]] = {
    "alerts_count": ("Alert Count", "count"),
}

# Mobile snapshots use this prefix so device_id distinguishes source (e.g. mobile:loc_lough_dan).
MOBILE_DEVICE_ID_PREFIX = "mobile:"


def _display_name_and_unit(field_key: str, display_map: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """Return (display name, unit); unknown keys get title-cased key and empty unit."""
    if field_key in display_map:
        return display_map[field_key]
    name = field_key.replace("_", " ").title()
    return name, ""


def mobile_to_snapshot(
    location_id: str,
    latest_point: TimeSeriesPoint | None,
    count_results: list[CountResult],
    *,
    device_id_prefix: str = MOBILE_DEVICE_ID_PREFIX,
) -> Snapshot:
    """
    Build a Snapshot from mobile data so it matches the PC snapshot shape.

    - device_id: prefix + location_id (e.g. mobile:loc_lough_dan)
    - timestamp_utc: from latest_point, or now if no point
    - metrics: one Metric per value in latest_point.values, plus one per count result.
    Status is always "normal" unless you add mobile thresholds later.
    """
    device_id = f"{device_id_prefix}{location_id}"
    if latest_point:
        ts_utc = datetime.fromtimestamp(latest_point.timestamp_millis / 1000.0, tz=timezone.utc)
    else:
        ts_utc = datetime.now(timezone.utc)

    metrics: list[Metric] = []
    for key, value in (latest_point.values if latest_point else {}).items():
        name, unit = _display_name_and_unit(key, _DISPLAY)
        metrics.append(Metric(name=name, value=float(value), unit=unit, status="normal"))
    for cr in count_results:
        name, unit = _display_name_and_unit(cr.metric_id, _COUNT_DISPLAY)
        metrics.append(Metric(name=name, value=float(cr.count), unit=unit, status="normal"))

    return Snapshot(device_id=device_id, timestamp_utc=ts_utc, metrics=metrics)


def mobile_history_to_snapshots(
    location_id: str,
    points: list[TimeSeriesPoint],
    count_results: list[CountResult],
    *,
    device_id_prefix: str = MOBILE_DEVICE_ID_PREFIX,
) -> list[Snapshot]:
    """
    Build a list of Snapshots from time-series points (same shape as PC historic).
    Each point becomes one snapshot; count metrics (e.g. Alert Count) are appended
    from count_results (same value for each point; counts are location-level).
    """
    out: list[Snapshot] = []
    for point in points:
        snap = mobile_to_snapshot(
            location_id, point, count_results, device_id_prefix=device_id_prefix
        )
        out.append(snap)
    return out
