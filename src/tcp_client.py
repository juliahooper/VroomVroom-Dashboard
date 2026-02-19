"""
TCP client – connects to the server, logs socket info, sends one JSON metric
payload (length-prefixed protocol), then closes. Uses RAII (closing) and
BlockTimer so sockets never leak and we log timing for serialise/transmit.
"""
from __future__ import annotations

import logging
import socket
from dataclasses import asdict

from .block_timer import BlockTimer
from .config import AppConfig
from .metrics_reader import MetricsError, read_metrics
from .models import create_snapshot, snapshot_to_json
from .protocol import encode_message
from .raii import closing

logger = logging.getLogger(__name__)
ENCODING = "utf-8"


def run_client(config: AppConfig) -> None:
    """
    Connect to server, log local/remote socket info, send one JSON metric
    message (4-byte length + payload), then close. Socket closed via closing() even on exception.
    """
    host = config.server_host
    port = config.server_port
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.connect((host, port))
        local = sock.getsockname()
        remote = sock.getpeername()
        logger.info(
            "Connected: local %s:%s, remote %s:%s",
            local[0], local[1], remote[0], remote[1],
        )
        metrics = read_metrics()
        thresholds = asdict(config.danger_thresholds)
        with BlockTimer("create_snapshot", log_level=logging.INFO):
            snapshot = create_snapshot(
                device_id=config.device_id,
                metrics_dict=metrics,
                thresholds=thresholds,
            )
        with BlockTimer("snapshot_to_json", log_level=logging.INFO):
            payload_str = snapshot_to_json(snapshot)
        payload_bytes = payload_str.encode(ENCODING)
        message = encode_message(payload_bytes)
        with BlockTimer("sendall", log_level=logging.INFO):
            sock.sendall(message)
        logger.info("Sent metric payload (%d bytes)", len(payload_bytes))
    logger.info("Socket closed")


def main(config_path: str | None = None) -> int:
    """Load config, set up logging, run the client once. Returns 0 on success."""
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
