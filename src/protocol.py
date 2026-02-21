"""
Simple application protocol: stream vs message.

TCP is a stream of bytes; we need to know where one message ends and the next begins.
Format: 4-byte header (payload length, big-endian) + payload bytes. The server
buffers incoming bytes and only processes complete messages.
"""
from __future__ import annotations

import struct

# Header is exactly 4 bytes; value is payload length (big-endian)
HEADER_SIZE = 4
HEADER_FORMAT = ">I"


def encode_message(payload: bytes) -> bytes:
    """
    Encode one message: 4-byte length header + payload.
    Receiver reads 4 bytes to get length, then reads that many payload bytes.
    """
    if len(payload) > 0xFFFFFFFF:
        raise ValueError("Payload too large for 4-byte length header")
    header = struct.pack(HEADER_FORMAT, len(payload))
    return header + payload


def decode_header(header: bytes) -> int:
    """Decode the 4-byte header to get payload length in bytes."""
    if len(header) != HEADER_SIZE:
        raise ValueError(f"Header must be {HEADER_SIZE} bytes, got {len(header)}")
    (length,) = struct.unpack(HEADER_FORMAT, header)
    return length


def extract_messages(buffer: bytearray) -> list[bytes]:
    """
    Consume complete messages from the front of the buffer. Each message is
    4-byte length + that many payload bytes. Modifies buffer in place (removes
    consumed bytes). Returns a list of payload byte strings.
    """
    messages: list[bytes] = []
    while True:
        if len(buffer) < HEADER_SIZE:
            break
        length = decode_header(bytes(buffer[:HEADER_SIZE]))
        if len(buffer) < HEADER_SIZE + length:
            break
        payload = bytes(buffer[HEADER_SIZE : HEADER_SIZE + length])
        del buffer[: HEADER_SIZE + length]
        messages.append(payload)
    return messages
