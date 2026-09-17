"""Determinism: the synthetic sources are the test harness, so they must not drift."""

from __future__ import annotations

import itertools
import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.sources.pattern import PATTERN_NAMES, PatternSource  # noqa: E402


def frames(pattern: str, n: int, **kwargs):
    source = PatternSource(pattern, **kwargs)
    return [g.rgb_bytes for g in itertools.islice(source.frames(), n)]


class TestDeterminism(unittest.TestCase):
    def test_every_pattern_repeats_exactly(self) -> None:
        for pattern in PATTERN_NAMES:
            with self.subTest(pattern=pattern):
                self.assertEqual(
                    frames(pattern, 5, width=24, height=12),
                    frames(pattern, 5, width=24, height=12),
                )

    def test_noise_is_seed_dependent(self) -> None:
        a = frames("noise", 2, width=16, height=16, seed=1)
        b = frames("noise", 2, width=16, height=16, seed=1)
        c = frames("noise", 2, width=16, height=16, seed=2)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_motion_patterns_change_between_frames(self) -> None:
        for pattern in ("square", "sweep", "noise"):
            with self.subTest(pattern=pattern):
                first, second = frames(pattern, 2, width=16, height=16)
                self.assertNotEqual(first, second)

    def test_bars_are_static(self) -> None:
        first, second = frames("bars", 2, width=24, height=12)
        self.assertEqual(first, second)

    def test_bars_have_the_expected_band_structure(self) -> None:
        grid = next(PatternSource("bars", width=70, height=30).frames())
        top = grid.rgb[: 30 * 2 // 3]
        ramp = grid.rgb[30 * 2 // 3 :]
        # seven bars means at least seven distinct colours across the top band
        colours = {tuple(int(v) for v in px) for px in top.reshape(-1, 3)[::7]}
        self.assertGreaterEqual(len(colours), 5)
        # the bottom strip is a left-to-right ramp: darker on the left than on the right
        self.assertLess(int(ramp[:, :5, 0].mean()), int(ramp[:, -5:, 0].mean()))

    def test_fps_and_index_drive_timestamps(self) -> None:
        source = PatternSource("bars", width=8, height=8, fps=4)
        grids = list(itertools.islice(source.frames(), 3))
        self.assertEqual([g.index for g in grids], [0, 1, 2])
        self.assertAlmostEqual(grids[2].t, 0.5)


if __name__ == "__main__":
    unittest.main()
