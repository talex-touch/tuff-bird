"""CRC-32C (Castagnoli), as TFRecord framing uses it.

A compiled implementation is used when one is installed (``crc32c`` or ``google-crc32c``);
otherwise a table-driven one in pure Python, which is fast enough for scalar events but slow
for large images.
"""

from __future__ import annotations

_POLY = 0x82F63B78


def _make_table() -> list[int]:
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ _POLY if crc & 1 else crc >> 1
        table.append(crc)
    return table


_TABLE = _make_table()


def _crc32c_python(data: bytes) -> int:
    crc = 0xFFFFFFFF
    table = _TABLE
    for byte in data:
        crc = table[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


try:  # pragma: no cover - depends on what is installed
    from crc32c import crc32c as _crc32c_fast  # type: ignore[import-not-found]

    def crc32c(data: bytes) -> int:
        return _crc32c_fast(data)
except ImportError:  # pragma: no cover
    try:
        import google_crc32c  # type: ignore[import-not-found]

        def crc32c(data: bytes) -> int:
            return google_crc32c.value(data)
    except ImportError:
        crc32c = _crc32c_python


def masked_crc32c(data: bytes) -> int:
    """The rotated, offset CRC TFRecord stores, so a CRC of a CRC does not look valid."""
    crc = crc32c(data)
    return (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & 0xFFFFFFFF
