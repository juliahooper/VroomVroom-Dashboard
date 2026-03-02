"""
Data types for mobile metrics consumed by CoC.

Clean interface so the rest of CoC can use these without knowing Firestore details.
All types are generic so new metrics and value fields can be added via config.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocationSummary:
    """One location (id = Firestore document id)."""
    id: str
    name: str
    county: str


@dataclass(frozen=True)
class TimeSeriesPoint:
    """
    One time-series point. Values dict keys come from config (e.g. risk_score, water_temp).
    Add new metrics by adding value_fields in mobile config; no code change.
    """
    timestamp_millis: int
    values: dict[str, float]  # metric field name -> value


@dataclass(frozen=True)
class CountResult:
    """Count metric for a location (metric_id from config, e.g. alerts_count)."""
    location_id: str
    metric_id: str
    count: int
    measured_at_millis: int
