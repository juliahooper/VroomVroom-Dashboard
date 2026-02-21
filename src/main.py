"""
Main entry point for the application.

What this does: loads config, sets up logging to console and file, reads system
metrics (CPU, RAM, disk), builds a snapshot with normal/warning/danger status,
serialises it to JSON, then round-trips back to verify the JSON is correct.
Exit codes: 0 = success, 1 = unexpected error, 2 = config error, 3 = metrics error, 4/5 = JSON error.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from .config import AppConfig, ConfigError, load_config
from .metrics_reader import MetricsError, read_metrics
from .models import (
    Snapshot,
    create_snapshot,
    get_status_summary,
    snapshot_from_json,
    snapshot_to_json,
)


def setup_logging(config: AppConfig) -> None:
    """
    Set up logging so messages go to both the console and a log file.
    Log level and file path come from config.
    """
    # Convert log level string to logging level constant
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    log_level = log_level_map.get(config.log_level.upper(), logging.INFO)

    log_path = Path(config.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def main() -> int:
    """
    Main function.
    
    Returns:
        0: Success
        1: Unexpected error
        2: Configuration failure
        3: Metric read failure
        4: JSON serialization/deserialization error
        5: JSON integrity verification failure
    """
    logger = logging.getLogger(__name__)
    
    # Log startup
    logger.info("Application starting up")
    
    # Load configuration
    config_path = os.environ.get("VROOMVROOM_CONFIG", str(Path("config") / "config.json"))
    try:
        logger.info(f"Loading configuration from: {config_path}")
        config = load_config(config_path)
        logger.info("Configuration loaded successfully")
    except ConfigError as e:
        # Use print for config errors since logging may not be set up yet
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    
    # Setup logging with config values
    setup_logging(config)
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"Logging configured - Level: {config.log_level}, File: {config.log_file_path}")
        
        # Log application info
        logger.info(f"Application: {config.app_name}")
        logger.info(f"Device ID: {config.device_id}")
        logger.info(f"Read interval: {config.read_interval_seconds} seconds")
        
        # Read metrics
        metrics = read_metrics()
        logger.info("Metrics read successfully")
        
        # Turn raw numbers into a Snapshot with normal/warning/danger per metric
        logger.info("Creating snapshot from metrics")
        thresholds_dict = asdict(config.danger_thresholds)
        snapshot = create_snapshot(
            device_id=config.device_id,
            metrics_dict=metrics,
            thresholds=thresholds_dict
        )
        logger.info(f"Snapshot created - Device: {snapshot.device_id}, Timestamp: {snapshot.timestamp_utc.isoformat()}")
        logger.info(f"Snapshot contains {len(snapshot.metrics)} metrics")

        # Precomputed status summary for later stretch-goal alerting
        status_summary = get_status_summary(snapshot)
        if status_summary.has_danger:
            logger.warning(
                f"Danger: {[m.name for m in status_summary.danger_metrics]}"
            )
        if status_summary.has_warning:
            logger.info(
                f"Warning: {[m.name for m in status_summary.warning_metrics]}"
            )

        for metric in snapshot.metrics:
            logger.debug(f"Metric: {metric.name} = {metric.value}{metric.unit} (Status: {metric.status})")
        
        # Serialize snapshot to JSON
        logger.info("Serializing snapshot to JSON")
        try:
            snapshot_json = snapshot_to_json(snapshot)
            logger.info(f"JSON serialization completed - {len(snapshot_json)} characters")
        except (json.JSONEncodeError, TypeError) as e:
            logger.error(f"Failed to serialize snapshot to JSON: {e}", exc_info=True)
            return 4

        logger.info("JSON payload:")
        logger.info(snapshot_json)
        
        # Deserialize to verify integrity
        logger.info("Deserializing JSON to verify integrity")
        try:
            deserialized_snapshot = snapshot_from_json(snapshot_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to deserialize JSON (malformed JSON): {e}", exc_info=True)
            return 4
        except ValueError as e:
            logger.error(f"JSON integrity verification failed (validation error): {e}", exc_info=True)
            return 5
        
        # Verify integrity by comparing key fields
        try:
            if deserialized_snapshot.device_id != snapshot.device_id:
                raise ValueError(f"Device ID mismatch: {deserialized_snapshot.device_id} != {snapshot.device_id}")
            if deserialized_snapshot.timestamp_utc != snapshot.timestamp_utc:
                raise ValueError(f"Timestamp mismatch: {deserialized_snapshot.timestamp_utc} != {snapshot.timestamp_utc}")
            if len(deserialized_snapshot.metrics) != len(snapshot.metrics):
                raise ValueError(f"Metrics count mismatch: {len(deserialized_snapshot.metrics)} != {len(snapshot.metrics)}")

            for i, (original, deserialized) in enumerate(zip(snapshot.metrics, deserialized_snapshot.metrics)):
                if original.name != deserialized.name:
                    raise ValueError(f"Metric {i} name mismatch: {deserialized.name} != {original.name}")
                if abs(original.value - deserialized.value) > 0.01:  # Allow small floating point differences
                    raise ValueError(f"Metric {i} value mismatch: {deserialized.value} != {original.value}")
                if original.unit != deserialized.unit:
                    raise ValueError(f"Metric {i} unit mismatch: {deserialized.unit} != {original.unit}")
                if original.status != deserialized.status:
                    raise ValueError(f"Metric {i} status mismatch: {deserialized.status} != {original.status}")
            
            logger.info("JSON integrity verification passed - deserialized snapshot matches original")
        except ValueError as e:
            logger.error(f"JSON integrity verification failed (data mismatch): {e}", exc_info=True)
            return 5
    except MetricsError as e:
        logger.error(f"Failed to read system metrics: {e}", exc_info=True)
        return 3
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    else:
        # Log shutdown
        logger.info("Application shutting down")
        return 0
    finally:
        logging.shutdown()  # Flush and close all handlers for clean exit


if __name__ == '__main__':
    sys.exit(main())
