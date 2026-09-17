"""Acceptance: stdlib PNG encoder is structurally correct."""

from __future__ import annotations

import pathlib
import struct
import sys
import unittest
import zlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.render.png import PNG_MAGIC, png_bytes  # noqa: E402


def _chunks(data: bytes):
    assert data.startswith(PNG_MAGIC)
    pos = len(PNG_MAGIC)
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        crc = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])[0]
        expect = zlib.crc32(tag + chunk) & 0xFFFFFFFF
        yield tag, chunk, crc, expect
        pos += 12 + length


class TestNovelPng(unittest.TestCase):
    def test_png_bytes_structure(self) -> None:
        w, h = 7, 5
        rgb = bytes((i * 3) % 256 for i in range(w * h * 3))
        data = png_bytes(rgb, w, h)
        self.assertTrue(data.startswith(PNG_MAGIC))

        idat_parts: list[bytes] = []
        saw_ihdr = saw_iend = False
        for tag, chunk, crc, expect in _chunks(data):
            self.assertEqual(crc, expect, tag)
            if tag == b"IHDR":
                saw_ihdr = True
                width, height, bit_depth, colour, comp, filt, inter = struct.unpack(
                    ">IIBBBBB", chunk
                )
                self.assertEqual((width, height), (w, h))
                self.assertEqual(bit_depth, 8)
                self.assertEqual(colour, 2)
                self.assertEqual((comp, filt, inter), (0, 0, 0))
            elif tag == b"IDAT":
                idat_parts.append(chunk)
            elif tag == b"IEND":
                saw_iend = True
        self.assertTrue(saw_ihdr and saw_iend)
        raw = zlib.decompress(b"".join(idat_parts))
        self.assertEqual(len(raw), h * (1 + 3 * w))
        for y in range(h):
            self.assertEqual(raw[y * (1 + 3 * w)], 0)


if __name__ == "__main__":
    unittest.main()
