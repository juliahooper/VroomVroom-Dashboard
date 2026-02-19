"""
RAII and resource lifecycle helpers.
- Use context managers (with) for sockets and files so they close even on exception.
- Avoids resource leaks and TIME_WAIT buildup from unclosed sockets.
- Use closing(socket.socket(...)) for RAII socket cleanup (see tcp_server, tcp_client).
"""
Plain language: when you use "with closing(socket.socket(...)) as sock:", Python
guarantees it will call sock.close() when the block ends—even if an error happens.
That way we don't leave sockets open (which can cause "address in use" / TIME_WAIT).
"""
from __future__ import annotations

import contextlib

# "closing" is a context manager: when you leave the "with" block it calls .close() on the object.
# Use it for sockets: with closing(socket.socket(...)) as sock: ...
closing = contextlib.closing
