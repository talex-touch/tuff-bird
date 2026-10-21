"""TFRecord framing: ``uint64 length | uint32 masked_crc(length) | data | uint32 masked_crc(data)``."""

from __future__ import annotations

import struct

from .crc32c import masked_crc32c

HEADER_SIZE = 12
FOOTER_SIZE = 4


def encode_record(data: bytes) -> bytes:
    header = struct.pack("<Q", len(data))
    return (
        header
        + struct.pack("<I", masked_crc32c(header))
        + data
        + struct.pack("<I", masked_crc32c(data))
    )


class CorruptRecordError(ValueError):
    pass


class RecordReader:
    """Reads records from a file that may still be growing.

    The reader remembers how far it got. A record whose bytes have not all arrived yet is left
    for the next call, so a live file can be polled without ever handing out half a record.
    The length CRC is always checked, which is what catches a torn or misaligned header; the
    data CRC is checked only when asked, because in pure Python it costs more than the parse.
    """

    def __init__(self, path: str, *, verify_data: bool = False) -> None:
        self.path = path
        self.offset = 0
        self.verify_data = verify_data

    def read_available(self, max_bytes: int = 64 * 1024 * 1024) -> list[bytes]:
        with open(self.path, "rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read(max_bytes)
        records: list[bytes] = []
        pos = 0
        size = len(chunk)
        while size - pos >= HEADER_SIZE:
            header = chunk[pos:pos + 8]
            (length,) = struct.unpack("<Q", header)
            (length_crc,) = struct.unpack("<I", chunk[pos + 8:pos + 12])
            if masked_crc32c(header) != length_crc:
                raise CorruptRecordError(f"{self.path}: bad length checksum at byte {self.offset + pos}")
            end = pos + HEADER_SIZE + length + FOOTER_SIZE
            if end > size:
                if pos == 0 and size == max_bytes:
                    # One record larger than the read window: widen the window for it.
                    return self.read_available(max_bytes=HEADER_SIZE + length + FOOTER_SIZE)
                break  # the rest of this record has not been written yet
            data = chunk[pos + HEADER_SIZE:pos + HEADER_SIZE + length]
            if self.verify_data:
                (data_crc,) = struct.unpack("<I", chunk[end - FOOTER_SIZE:end])
                if masked_crc32c(data) != data_crc:
                    raise CorruptRecordError(f"{self.path}: bad data checksum at byte {self.offset + pos}")
            records.append(data)
            pos = end
        self.offset += pos
        return records
