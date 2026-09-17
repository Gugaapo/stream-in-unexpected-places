"""Acceptance: change gate skips identical frames unless chat advances."""

from __future__ import annotations

import itertools
import pathlib
import sys
import tempfile
import time
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.describe import ScriptedDescriber  # noqa: E402
from streamkit.grid import Grid  # noqa: E402
from streamkit.novel import should_describe  # noqa: E402
from streamkit.sinks.novel import NovelTxtSink  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402


class TestNovelChangeGate(unittest.TestCase):
    def test_identical_frames_one_call_then_chat_or_change_makes_two(self) -> None:
        paragraphs = [f"p{i}" for i in range(10)]
        describer = ScriptedDescriber(paragraphs, sleep=0.0)
        source = PatternSource("bars", width=40, height=24, fps=10)
        grids = list(itertools.islice(source.frames(), 1))
        first = grids[0]

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "novel.md"
            sink = NovelTxtSink(
                interval=0.0,
                change_threshold=1.5,
                describer=describer,
                out_path=out,
                no_chat=True,
                stream=open(pathlib.Path(tmp) / "stdout.txt", "w", encoding="utf-8"),
            )
            sink.open(40, 24)
            # 20 identical frames (same rgb).
            for i in range(20):
                g = Grid(first.rgb.copy(), index=i, t=i / 10.0, meta=dict(first.meta))
                sink.write(g)
                time.sleep(0.02)  # let worker finish the first call
            time.sleep(0.05)
            self.assertEqual(len(describer.calls), 1)

            # Frame that differs above threshold.
            other = next(PatternSource("noise", width=40, height=24, fps=10, seed=99).frames())
            sink.write(other.with_index(21))
            time.sleep(0.05)
            self.assertEqual(len(describer.calls), 2)
            sink.close()
            sink._stream.close()

    def test_should_describe_pure_gate(self) -> None:
        a = next(PatternSource("bars", width=16, height=8, fps=1).frames())
        b = Grid(a.rgb.copy(), index=1, t=1.0, meta=dict(a.meta))
        self.assertFalse(should_describe(a, b, [], 0, threshold=1.5))
        self.assertTrue(should_describe(a, b, [("u", "hi")], 0, threshold=1.5))
        noise = next(PatternSource("noise", width=16, height=8, fps=1, seed=7).frames())
        self.assertTrue(should_describe(a, noise, [], 0, threshold=1.5))


if __name__ == "__main__":
    unittest.main()
