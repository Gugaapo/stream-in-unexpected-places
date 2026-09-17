"""Grid resampling: exactness of the area filter, and byte-identity with the ported sampler."""

from __future__ import annotations

import pathlib
import sys
import unittest

import numpy as np

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.grid import Grid  # noqa: E402
from streamkit.render import terminal  # noqa: E402


def ramp_grid(w: int, h: int) -> Grid:
    """A grid where every pixel encodes its own coordinates, so mistakes are visible."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :, 0] = np.arange(w, dtype=np.uint8)[None, :]
    arr[:, :, 1] = np.arange(h, dtype=np.uint8)[:, None]
    arr[:, :, 2] = 7
    return Grid(arr)


class TestAreaResize(unittest.TestCase):
    def test_4x4_to_2x2_is_quadrant_mean(self) -> None:
        arr = np.arange(16, dtype=np.uint8).reshape(4, 4, 1).repeat(3, axis=2)
        out = Grid(arr).resize(2, 2, method="area")
        expected = np.array([[2.5, 4.5], [10.5, 12.5]], dtype=np.float32)
        got = out.rgb[:, :, 0].astype(np.float32)
        np.testing.assert_allclose(got, expected, atol=0.5)
        self.assertEqual(out.rgb.dtype, np.uint8)
        self.assertEqual((out.width, out.height), (2, 2))

    def test_area_downscale_preserves_average(self) -> None:
        grid = ramp_grid(64, 32)
        small = grid.resize(8, 4, method="area")
        # a flat-ish region must stay within a few levels of the original
        self.assertLess(abs(float(small.rgb[:, :, 2].mean()) - 7.0), 1.0)
        self.assertEqual((small.width, small.height), (8, 4))

    def test_area_upscale_shape_and_dtype(self) -> None:
        out = ramp_grid(4, 4).resize(9, 7, method="area")
        self.assertEqual((out.width, out.height), (9, 7))
        self.assertEqual(out.rgb.shape, (7, 9, 3))
        self.assertEqual(out.rgb.dtype, np.uint8)


class TestNearestResize(unittest.TestCase):
    def test_matches_ported_sampler_byte_for_byte(self) -> None:
        rng = np.random.default_rng(0)
        arr = rng.integers(0, 256, size=(5, 7, 3), dtype=np.uint8)
        grid = Grid(arr)
        for dst_w, dst_h in ((3, 4), (14, 10), (1, 1)):
            mine = grid.resize(dst_w, dst_h, method="nearest")
            theirs = terminal.resize_rgb(grid.rgb_bytes, 7, 5, dst_w, dst_h)
            self.assertEqual(mine.rgb_bytes, theirs, f"mismatch at {dst_w}x{dst_h}")

    def test_identity_returns_same_object(self) -> None:
        grid = ramp_grid(6, 6)
        self.assertIs(grid.resize(6, 6), grid)

    def test_unknown_method_raises(self) -> None:
        with self.assertRaises(ValueError):
            ramp_grid(4, 4).resize(2, 2, method="lanczos-ish")


class TestGridBasics(unittest.TestCase):
    def test_from_raw_roundtrip(self) -> None:
        grid = ramp_grid(5, 3)
        back = Grid.from_raw(grid.rgb_bytes, 5, 3, index=9)
        self.assertEqual(back.rgb_bytes, grid.rgb_bytes)
        self.assertEqual(back.index, 9)
        self.assertEqual((back.width, back.height), (5, 3))

    def test_from_raw_rejects_short_buffer(self) -> None:
        with self.assertRaises(ValueError):
            Grid.from_raw(b"\x00" * 10, 4, 4)

    def test_rejects_bad_shape(self) -> None:
        with self.assertRaises(ValueError):
            Grid(np.zeros((4, 4), dtype=np.uint8))

    def test_save_ppm_header(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = ramp_grid(4, 2).save_ppm(pathlib.Path(tmp) / "a.ppm")
            raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"P6\n4 2\n255\n"))
        self.assertEqual(len(raw), len(b"P6\n4 2\n255\n") + 4 * 2 * 3)


if __name__ == "__main__":
    unittest.main()
