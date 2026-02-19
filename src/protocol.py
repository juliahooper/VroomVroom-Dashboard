"""
Simple application protocol: stream vs message.

Format:
- 4-byte fixed-length header (big-endian unsigned int = payload length, zero-padded)
- Followed by payload (e.g. JSON string as UTF-8 bytes)

Enables receivers to buffer incoming bytes and process only complete messages.
"""
from __future__ import annotations

import struct

# Header is exactly 4 bytes; value is payload length (big-endian, zero-padded in high bytes)
HEADER_SIZE = 4
HEADER_FORMAT = ">I"  # big-endian unsigned int


def encode_message(payload: bytes) -> bytes:
    """
    Encode one message: 4-byte length header (zero-padded) + payload.

    Args:
        payload: Raw payload bytes (e.g. JSON string encoded as UTF-8).

    Returns:
        Header (4 bytes) + payload. Receiver can read 4 bytes to get length, then read that many bytes.
    """
    if len(payload) > 0xFFFFFFFF:
        raise ValueError("Payload too large for 4-byte length header")
    header = struct.pack(HEADER_FORMAT, len(payload))
    return header + payload


def decode_header(header: bytes) -> int:
    """
    Decode the 4-byte header to payload length.

    Args:
        header: Exactly HEADER_SIZE (4) bytes.

    Returns:
        Payload length in bytes.

    Raises:
        ValueError: If len(header) != HEADER_SIZE.
    """
    if len(header) != HEADER_SIZE:
        raise ValueError(f"Header must be {HEADER_SIZE} bytes, got {len(header)}")
    (length,) = struct.unpack(HEADER_FORMAT, header)
    return length


def extract_messages(buffer: bytearray) -> list[bytes]:
    """
    Consume complete messages from the front of buffer.
    Each message is 4-byte length + that many payload bytes.
    Modifies buffer in place: removes consumed bytes.

    Args:
        buffer: Mutable buffer of received bytes.

    Returns:
        List of payload byte strings (one per complete message). Buffer is shortened by the size of extracted messages.
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
