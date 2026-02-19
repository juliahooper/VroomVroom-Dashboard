"""
TCP server – listens on a port, accepts connections, reads length-prefixed
messages and logs the JSON payload. Uses RAII (closing) so sockets are always
closed and no socket leaks occur.
"""
from __future__ import annotations

import json
import logging
import socket

from .config import AppConfig
from .protocol import extract_messages
from .raii import closing

logger = logging.getLogger(__name__)

RECV_SIZE = 4096


def _handle_client(conn: socket.socket, address: tuple[str, int]) -> None:
    """
    Read from one client until the connection closes. Buffer bytes and only
    process complete messages (4-byte header + payload). Log each JSON message.
    Caller uses closing(conn) so the socket is always closed.
    """
    peer = f"{address[0]}:{address[1]}"
    logger.info("Client connected: %s", peer)
    buffer: bytearray = bytearray()
    try:
        while True:
            data = conn.recv(RECV_SIZE)
            if not data:
                break
            buffer.extend(data)
            for payload in extract_messages(buffer):
                try:
                    text = payload.decode("utf-8")
                    obj = json.loads(text)
                    logger.info("Message from %s: %s", peer, json.dumps(obj, indent=2))
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning("Invalid message from %s: %r (error: %s)", peer, payload[:200], e)
    finally:
        logger.info("Connection closed: %s", peer)


def run_server(config: AppConfig, *, host: str = "0.0.0.0") -> None:
    """
    Run the TCP server: listen on config.server_port, accept connections,
    read and log data from each client. Uses closing() so no socket leaks.
    """
    port = config.server_port
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as listen_sock:
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind((host, port))
        listen_sock.listen()
        logger.info("TCP server listening on %s:%s", host, port)
        while True:
            conn, address = listen_sock.accept()
            with closing(conn):
                try:
                    _handle_client(conn, address)
                except OSError as e:
                    logger.warning("Error handling client %s: %s", address, e)
    logger.info("Server socket closed")


def main(config_path: str | None = None) -> int:
    """Load config, set up logging, run the TCP server. Returns 0 on success."""
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
    logger.info("Starting TCP server (port %s)", config.server_port)
    try:
        run_server(config)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except OSError as e:
        logger.error("Server error: %s", e, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
