"""
Main entry point for the application.

Execution order: main() runs top-to-bottom—load config, set up logging, read
metrics, build snapshot, serialise to JSON, verify integrity, then exit. See
docs/EXECUTION_ORDER.md.

Exit codes: 0 = success, 1 = unexpected error, 2 = config error, 3 = metrics error, 4/5 = JSON error.

CLI: argparse for --config (config file path). Env VROOMVROOM_CONFIG overrides default if not passed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from .configlib import AppConfig, ConfigError, load_config, setup_logging
from .metrics_reader import MetricsError, read_metrics
from .datasnapshot import (
    Snapshot,
    create_snapshot,
    get_status_summary,
    snapshot_from_json,
    snapshot_to_json,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments. Used by main() and testable with explicit argv."""
    parser = argparse.ArgumentParser(
        description="VroomVroom: read OS metrics, build snapshot, serialise to JSON and verify round-trip.",
        prog="python -m src.main",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=os.environ.get("VROOMVROOM_CONFIG", str(Path("config") / "config.json")),
        help="Path to config JSON (default: config/config.json or VROOMVROOM_CONFIG)",
    )
    parser.add_argument(
        "--agent",
        "-a",
        action="store_true",
        help="Run as long-running collector agent: read metrics every interval, upload via API. Use with --interval. Graceful shutdown on SIGTERM/SIGINT.",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Collector loop interval in seconds (default: read_interval_seconds from config). Used with --agent.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
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
    args = _parse_args(argv)

    # Log startup
    logger.info("Application starting up")

    # Load configuration (CLI --config takes precedence over env)
    config_path = args.config
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

    # Agent mode: continuous loop, upload via API (system metrics + YouTube), graceful shutdown
    if args.agent:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # for YOUTUBE_API_KEY
        interval = args.interval if args.interval is not None else config.read_interval_seconds
        if interval <= 0:
            logger.error("Interval must be positive (got %s)", interval)
            return 2
        api_url = os.environ.get("VROOMVROOM_API_URL", "http://127.0.0.1:5000")
        try:
            from .collector_agent import run_agent
            run_agent(config, interval_seconds=interval, api_base_url=api_url, config_path=config_path)
        except Exception as e:
            logger.error("Agent failed: %s", e, exc_info=True)
            logging.shutdown()
            return 1
        logging.shutdown()
        logger.info("Application shutting down")
        return 0

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


# Entry point: only run when this module is executed (e.g. python -m src.main),
# not when imported. See docs/EXECUTION_ORDER.md.
if __name__ == "__main__":
    sys.exit(main())
