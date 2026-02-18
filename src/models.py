"""
Data models and schemas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


# Status type for metrics
MetricStatus = Literal["normal", "warning", "danger"]


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
            threshold = thresholds.get(metric_key, 100)
            
            # Determine status based on threshold
            if metric_value >= threshold:
                status: MetricStatus = "danger"
            elif metric_value >= threshold * 0.8:  # Warning at 80% of threshold
                status = "warning"
            else:
                status = "normal"
            
            metric = Metric(
                name=config['name'],
                value=metric_value,
                unit=config['unit'],
                status=status
            )
            metric_list.append(metric)
    
    return Snapshot(
        device_id=device_id,
        timestamp_utc=datetime.now(timezone.utc),
        metrics=metric_list
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
