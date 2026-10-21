"""The slice of the protobuf wire format that TensorBoard event files need.

Writing is a handful of field encoders. Reading is one generic field iterator: every message
here is decoded by walking its fields and keeping the numbers it knows, so a field added by a
newer writer is skipped instead of breaking the read.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator

VARINT = 0
FIXED64 = 1
LENGTH = 2
FIXED32 = 5


def encode_varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64  # negative int64 is encoded as its 64-bit two's complement
    out = bytearray()
    while True:
        bits = value & 0x7F
        value >>= 7
        if value:
            out.append(bits | 0x80)
        else:
            out.append(bits)
            return bytes(out)


def _key(field: int, wire_type: int) -> bytes:
    return encode_varint((field << 3) | wire_type)


def field_varint(field: int, value: int) -> bytes:
    return _key(field, VARINT) + encode_varint(int(value))


def field_double(field: int, value: float) -> bytes:
    return _key(field, FIXED64) + struct.pack("<d", value)


def field_float(field: int, value: float) -> bytes:
    return _key(field, FIXED32) + struct.pack("<f", value)


def field_bytes(field: int, value: bytes) -> bytes:
    return _key(field, LENGTH) + encode_varint(len(value)) + value


def field_string(field: int, value: str) -> bytes:
    return field_bytes(field, value.encode("utf-8"))


def decode_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def iter_fields(buf: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    """Yields ``(field, wire_type, value)``; varints come back as int, everything else as bytes."""
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = decode_varint(buf, pos)
        field, wire_type = key >> 3, key & 7
        if wire_type == VARINT:
            value, pos = decode_varint(buf, pos)
            yield field, wire_type, value
        elif wire_type == FIXED64:
            yield field, wire_type, buf[pos:pos + 8]
            pos += 8
        elif wire_type == LENGTH:
            size, pos = decode_varint(buf, pos)
            yield field, wire_type, buf[pos:pos + size]
            pos += size
        elif wire_type == FIXED32:
            yield field, wire_type, buf[pos:pos + 4]
            pos += 4
        else:
            raise ValueError(f"unsupported wire type {wire_type}")
        if pos > end:
            raise ValueError("truncated field")


def as_int64(value: int) -> int:
    return value - (1 << 64) if value >= 1 << 63 else value


def as_double(raw: bytes) -> float:
    return struct.unpack("<d", raw)[0]


def as_float(raw: bytes) -> float:
    return struct.unpack("<f", raw)[0]
