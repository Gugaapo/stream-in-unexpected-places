"""The shared run loop: frame limits, pacing, and closing on every path."""

from __future__ import annotations

import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.pipeline import RunResult, frame_limit, run  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402


class RecordingSink:
    """Minimal sink: counts frames, records close()."""

    def __init__(self) -> None:
        self.frames = 0
        self.opened: tuple[int, int] | None = None
        self.closed = 0

    def open(self, width: int, height: int) -> None:
        self.opened = (width, height)

    def write(self, grid) -> None:
        self.frames += 1

    def close(self) -> None:
        self.closed += 1


class ExplodingSource(PatternSource):
    """A source whose frame loop is interrupted (as Ctrl+C does)."""

    def frames(self):
        for grid in super().frames():
            yield grid
            raise KeyboardInterrupt


class TestFrameLimit(unittest.TestCase):
    def test_seconds_becomes_a_frame_count(self) -> None:
        self.assertEqual(frame_limit(fps=10, seconds=0.5, frames=None), 5)

    def test_the_lower_limit_wins(self) -> None:
        self.assertEqual(frame_limit(fps=10, seconds=10, frames=3), 3)
        self.assertEqual(frame_limit(fps=10, seconds=1, frames=30), 10)

    def test_no_seconds_means_no_limit(self) -> None:
        self.assertIsNone(frame_limit(fps=10, seconds=None, frames=None))
        self.assertEqual(frame_limit(fps=10, seconds=None, frames=7), 7)


class TestRun(unittest.TestCase):
    def test_frame_limit_is_honoured_and_both_ends_are_closed(self) -> None:
        source = PatternSource("bars", width=16, height=8, fps=10)
        sink = RecordingSink()
        result = run(source, sink, fps=10, pace="fast", frames=4)
        self.assertIsInstance(result, RunResult)
        self.assertEqual(result.frames, 4)
        self.assertEqual(sink.frames, 4)
        self.assertEqual(sink.closed, 1)
        self.assertFalse(result.interrupted)

    def test_seconds_limit_matches_fps(self) -> None:
        sink = RecordingSink()
        result = run(
            PatternSource("noise", width=8, height=4, fps=20),
            sink,
            fps=20,
            pace="fast",
            seconds=0.5,
        )
        self.assertEqual(result.frames, 10)

    def test_interrupt_still_closes_the_sink(self) -> None:
        sink = RecordingSink()
        source = ExplodingSource("square", width=8, height=4, fps=10)
        result = run(source, sink, fps=10, pace="fast")
        self.assertTrue(result.interrupted)
        self.assertEqual(sink.closed, 1)
        self.assertGreaterEqual(result.frames, 1)

    def test_unknown_pace_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run(PatternSource("bars", width=8, height=4), RecordingSink(), pace="turbo")


if __name__ == "__main__":
    unittest.main()
