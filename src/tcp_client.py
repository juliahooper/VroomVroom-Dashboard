"""
TCP client – metric transmission.

Connects to the server, logs local/remote socket info,
sends serialised JSON metric payloads, and closes the socket properly.
"""
from __future__ import annotations

import logging
import socket
from dataclasses import asdict

from .config import AppConfig
from .metrics_reader import MetricsError, read_metrics
from .models import create_snapshot, snapshot_to_json

logger = logging.getLogger(__name__)

# UTF-8 encoding for JSON payloads
ENCODING = "utf-8"


def run_client(config: AppConfig) -> None:
    """
    Connect to the server, log socket information, send one JSON metric
    payload (device_id, timestamp, metrics with status), then close.
    Socket is closed safely even on exception.
    """
    host = config.server_host
    port = config.server_port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
        # Log local and remote socket information
        local = sock.getsockname()
        remote = sock.getpeername()
        logger.info(
            "Connected: local %s:%s, remote %s:%s",
            local[0], local[1], remote[0], remote[1],
        )
        # Build and send serialised JSON metric payload
        metrics = read_metrics()
        thresholds = asdict(config.danger_thresholds)
        snapshot = create_snapshot(
            device_id=config.device_id,
            metrics_dict=metrics,
            thresholds=thresholds,
        )
        payload = snapshot_to_json(snapshot)
        data = payload.encode(ENCODING)
        sock.sendall(data)
        logger.info("Sent metric payload (%d bytes)", len(data))
    finally:
        sock.close()
        logger.info("Socket closed")


def main(config_path: str | None = None) -> int:
    """
    Load config, set up logging, run the client once.
    Returns 0 on success, non-zero on error.
    """
    import os
    import sys
    from pathlib import Path

    from .config import ConfigError, load_config
    from .main import setup_logging

    config_path = config_path or os.environ.get(
        "VROOMVROOM_CONFIG", str(Path("config") / "config.json")
    )
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    setup_logging(config)
    try:
        run_client(config)
    except (ConnectionRefusedError, OSError) as e:
        logger.error("Connection failed: %s", e, exc_info=True)
        return 3
    except MetricsError as e:
        logger.error("Failed to read metrics: %s", e, exc_info=True)
        return 4
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
