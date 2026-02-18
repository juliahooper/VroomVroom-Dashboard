"""
Data models and schemas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


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
