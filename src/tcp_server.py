"""
TCP server – low-level IPC foundation.

Understanding:
- Listening socket: one per server. bind(port), listen(), then accept() in a loop.
- Connection socket: one per client. Returned by accept(). Used to recv()/send(); close when done.
"""
from __future__ import annotations

import logging
import socket

from .config import AppConfig

logger = logging.getLogger(__name__)

# Size of buffer for each recv() call
RECV_SIZE = 4096


def _handle_client(conn: socket.socket, address: tuple[str, int]) -> None:
    """
    Read data from a single client until the connection is closed.
    Logs received data. Closes the connection socket safely.
    """
    peer = f"{address[0]}:{address[1]}"
    logger.info("Client connected: %s", peer)
    try:
        while True:
            data = conn.recv(RECV_SIZE)
            if not data:
                break
            logger.info("Received from %s: %r", peer, data)
    finally:
        conn.close()
        logger.info("Connection closed: %s", peer)


def run_server(config: AppConfig, *, host: str = "0.0.0.0") -> None:
    """
    Run the TCP server: listen on config.server_port, accept connections,
    read and log data from each client, then close sockets safely.

    Args:
        config: Application config (uses config.server_port).
        host: Bind address. Use "0.0.0.0" to accept from any interface.
    """
    port = config.server_port
    # Listening socket: one per server, bound to a port
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listen_sock.bind((host, port))
        listen_sock.listen()
        logger.info("TCP server listening on %s:%s", host, port)
        while True:
            # accept() blocks until a client connects; returns a new connection socket
            conn, address = listen_sock.accept()
            try:
                _handle_client(conn, address)
            except OSError as e:
                logger.warning("Error handling client %s: %s", address, e)
                try:
                    conn.close()
                except OSError:
                    pass
    finally:
        listen_sock.close()
        logger.info("Server socket closed")


def main(config_path: str | None = None) -> int:
    """
    Load config, set up logging, and run the TCP server.
    Returns 0 on normal exit, non-zero on error.
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
    # When run as script, ensure package context for relative imports
    sys.exit(main())
