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

# Default display names and units for known fields (config-driven value_fields
# not listed here get a title-cased name and empty unit).
_DISPLAY: dict[str, tuple[str, str]] = {
    "risk_score": ("Risk score", ""),
    "water_temp": ("Water temp", "°C"),
}

# Default display names for count metric_ids.
_COUNT_DISPLAY: dict[str, tuple[str, str]] = {
    "alerts_count": ("Alerts count", ""),
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
