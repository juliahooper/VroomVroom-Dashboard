"""
Main entry point for the application.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from config import AppConfig, ConfigError, load_config
from metrics_reader import MetricsError, read_metrics
from models import Snapshot, create_snapshot


def setup_logging(config: AppConfig) -> None:
    """
    Configure logging with console and file handlers.
    
    Uses log_level and log_file_path from config.
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
    
    # Create log directory if it doesn't exist
    log_path = Path(config.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create formatter
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
    """Main function."""
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
    logger.info(f"Logging configured - Level: {config.log_level}, File: {config.log_file_path}")
    
    # Log application info
    logger.info(f"Application: {config.app_name}")
    logger.info(f"Device ID: {config.device_id}")
    logger.info(f"Read interval: {config.read_interval_seconds} seconds")
    
    # Read metrics
    try:
        metrics = read_metrics()
        logger.info("Metrics read successfully")
        
        # Create snapshot with data models
        logger.info("Creating snapshot from metrics")
        thresholds_dict = asdict(config.danger_thresholds)
        snapshot = create_snapshot(
            device_id=config.device_id,
            metrics_dict=metrics,
            thresholds=thresholds_dict
        )
        logger.info(f"Snapshot created - Device: {snapshot.device_id}, Timestamp: {snapshot.timestamp_utc.isoformat()}")
        logger.info(f"Snapshot contains {len(snapshot.metrics)} metrics")
        
        # Log metric details
        for metric in snapshot.metrics:
            logger.debug(f"Metric: {metric.name} = {metric.value}{metric.unit} (Status: {metric.status})")
        
        # Create JSON from snapshot (for future API transmission)
        logger.info("Creating JSON from snapshot")
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
        snapshot_json = json.dumps(snapshot_dict, indent=2)
        logger.debug(f"JSON created: {len(snapshot_json)} characters")
        logger.info("JSON creation completed")
    except MetricsError as e:
        logger.error(f"Failed to read system metrics: {e}", exc_info=True)
        return 3
    except (json.JSONEncodeError, TypeError) as e:
        logger.error(f"Failed to create JSON from snapshot: {e}", exc_info=True)
        return 4
    except Exception as e:
        logger.error(f"Unexpected error reading metrics or creating snapshot: {e}", exc_info=True)
        return 1
    
    # Log shutdown
    logger.info("Application shutting down")
    return 0


if __name__ == '__main__':
    sys.exit(main())
