"""
Data models and schemas for metrics and snapshots.

Defines the shape of our data (Metric, Snapshot), turns raw numbers from the
metrics reader into snapshots with a status (normal/warning/danger), and
converts snapshots to/from JSON for logging or sending over the network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


# Status type for metrics
MetricStatus = Literal["normal", "warning", "danger"]

# Default fraction of danger threshold at which warning is raised (e.g. 0.8 = 80% of threshold)
DEFAULT_WARNING_FRACTION = 0.8


def compute_metric_status(
    value: float,
    danger_threshold: int,
    warning_fraction: float = DEFAULT_WARNING_FRACTION,
) -> MetricStatus:
    """
    Precompute danger status from a metric value and config thresholds.

    Supports later stretch goal alerting by centralizing status logic.
    - danger: value >= danger_threshold
    - warning: value >= danger_threshold * warning_fraction (but below danger)
    - normal: otherwise

    Args:
        value: Current metric value (e.g. percentage).
        danger_threshold: Config threshold above which status is "danger".
        warning_fraction: Fraction of danger_threshold for "warning" band (default 0.8).

    Returns:
        "normal", "warning", or "danger".
    """
    if value >= danger_threshold:
        return "danger"
    if value >= danger_threshold * warning_fraction:
        return "warning"
    return "normal"


@dataclass(frozen=True)
class Metric:
    """Represents a single system metric measurement."""
    name: str
    value: float
    unit: str
    status: MetricStatus


@dataclass(frozen=True)
class Snapshot:
    """Represents a snapshot of system metrics at a specific point in time."""
    device_id: str
    timestamp_utc: datetime
    metrics: list[Metric]


def create_snapshot(
    device_id: str,
    metrics_dict: dict[str, float],
    thresholds: dict[str, int]
) -> Snapshot:
    """
    Create a Snapshot from raw metrics dictionary.

    Args:
        device_id: Identifier for the device/system
        metrics_dict: Dictionary with metric names as keys and values as floats
        thresholds: Dictionary with metric names as keys and threshold percentages as values

    Returns:
        Snapshot object with Metric objects populated with status based on thresholds
    """
    metric_list: list[Metric] = []

    # Define metric metadata
    metric_configs = {
        'cpu_percent': {'name': 'CPU Usage', 'unit': '%'},
        'ram_percent': {'name': 'RAM Usage', 'unit': '%'},
        'disk_percent': {'name': 'Disk Usage', 'unit': '%'},
    }

    for metric_key, metric_value in metrics_dict.items():
        if metric_key in metric_configs:
            config = metric_configs[metric_key]
            danger_threshold = thresholds.get(metric_key, 100)
            status = compute_metric_status(
                value=metric_value,
                danger_threshold=danger_threshold,
            )
            metric = Metric(
                name=config['name'],
                value=metric_value,
                unit=config['unit'],
                status=status
            )
            metric_list.append(metric)

    # Snapshot is immutable: device id, current UTC time, and the list of metrics
    return Snapshot(
        device_id=device_id,
        timestamp_utc=datetime.now(timezone.utc),
        metrics=metric_list
    )


@dataclass(frozen=True)
class StatusSummary:
    """
    Precomputed summary of metric statuses for a snapshot.
    Use for stretch-goal alerting without re-applying thresholds.
    """
    danger_metrics: tuple[Metric, ...]
    warning_metrics: tuple[Metric, ...]
    normal_metrics: tuple[Metric, ...]
    has_danger: bool
    has_warning: bool


def get_status_summary(snapshot: Snapshot) -> StatusSummary:
    """
    Build a status summary from a snapshot's precomputed metric statuses.

    Enables alerting to check has_danger/has_warning and list affected metrics
    without re-reading config or recomputing thresholds.

    Args:
        snapshot: Snapshot with metrics that already have status set.

    Returns:
        StatusSummary with danger_metrics, warning_metrics, normal_metrics,
        has_danger, and has_warning.
    """
    danger: list[Metric] = []
    warning: list[Metric] = []
    normal: list[Metric] = []
    for m in snapshot.metrics:
        if m.status == "danger":
            danger.append(m)
        elif m.status == "warning":
            warning.append(m)
        else:
            normal.append(m)
    return StatusSummary(
        danger_metrics=tuple(danger),
        warning_metrics=tuple(warning),
        normal_metrics=tuple(normal),
        has_danger=len(danger) > 0,
        has_warning=len(warning) > 0,
    )


def snapshot_to_json(snapshot: Snapshot, indent: int | None = 2) -> str:
    """
    Serialize a Snapshot object to JSON string.

    Args:
        snapshot: Snapshot object to serialize
        indent: Number of spaces for indentation (None for compact JSON)

    Returns:
        JSON string representation of the snapshot
    """
    snapshot_dict = {
        "device_id": snapshot.device_id,
        "timestamp_utc": snapshot.timestamp_utc.isoformat(),
        "metrics": [
            {
                "name": m.name,
                "value": m.value,
                "unit": m.unit,
                "status": m.status
            }
            for m in snapshot.metrics
        ]
    }
    return json.dumps(snapshot_dict, indent=indent)


def snapshot_from_json(json_str: str) -> Snapshot:
    """
    Deserialize a JSON string to a Snapshot object.

    Args:
        json_str: JSON string representation of a snapshot

    Returns:
        Snapshot object reconstructed from JSON

    Raises:
        ValueError: If JSON is invalid or missing required fields
        json.JSONDecodeError: If JSON string is malformed
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Let JSONDecodeError propagate so callers can distinguish parsing errors from validation errors
        raise

    # Validate required fields
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")

    required_fields = ["device_id", "timestamp_utc", "metrics"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    if not isinstance(data["metrics"], list):
        raise ValueError("Field 'metrics' must be an array")

    # Parse timestamp
    try:
        timestamp = datetime.fromisoformat(data["timestamp_utc"])
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid timestamp format: {e}") from e

    # Parse metrics
    metric_list: list[Metric] = []
    for metric_data in data["metrics"]:
        if not isinstance(metric_data, dict):
            raise ValueError("Each metric must be an object")

        metric_required_fields = ["name", "value", "unit", "status"]
        for field in metric_required_fields:
            if field not in metric_data:
                raise ValueError(f"Metric missing required field: {field}")

        # Validate status
        if metric_data["status"] not in ("normal", "warning", "danger"):
            raise ValueError(f"Invalid status value: {metric_data['status']}")

        metric = Metric(
            name=str(metric_data["name"]),
            value=float(metric_data["value"]),
            unit=str(metric_data["unit"]),
            status=metric_data["status"]  # type: ignore[assignment]
        )
        metric_list.append(metric)

    return Snapshot(
        device_id=str(data["device_id"]),
        timestamp_utc=timestamp,
        metrics=metric_list
    )
