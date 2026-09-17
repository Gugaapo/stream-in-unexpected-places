"""Stdlib-only RGB8 PNG encoder (no Pillow).

Used by the novel sink so vision APIs can accept a still — PPM is not accepted.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return length + tag + data + crc


def png_bytes(rgb: bytes, width: int, height: int) -> bytes:
    """Encode packed RGB24 bytes into a PNG (8-bit, colour type 2, filter 0)."""
    w, h = int(width), int(height)
    expected = w * h * 3
    if len(rgb) != expected:
        raise ValueError(f"rgb length {len(rgb)} != {expected} for {w}x{h}")
    if w < 1 or h < 1:
        raise ValueError("width and height must be >= 1")

    # Filter type 0 (None) before each scanline.
    raw = bytearray(h * (1 + 3 * w))
    stride = 3 * w
    for y in range(h):
        row_start = y * (1 + stride)
        raw[row_start] = 0
        src = y * stride
        raw[row_start + 1 : row_start + 1 + stride] = rgb[src : src + stride]

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), level=9)
    return PNG_MAGIC + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def write_png(path: str | Path, rgb: bytes, width: int, height: int) -> Path:
    """Write ``png_bytes(...)`` to ``path``; create parent dirs as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(png_bytes(rgb, width, height))
    return p
