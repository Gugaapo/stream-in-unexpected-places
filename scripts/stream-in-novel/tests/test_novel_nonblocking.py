"""Acceptance: write() stays non-blocking even when the describer is slow."""

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
from stream_in_novel.sinks.novel import NovelTxtSink  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402


class TestNovelNonblocking(unittest.TestCase):
    def test_write_does_not_wait_on_slow_describer(self) -> None:
        describer = ScriptedDescriber(
            ["one", "two", "three", "four", "five"],
            sleep=1.0,
        )
        source = PatternSource("bars", width=64, height=36, fps=30)
        with tempfile.TemporaryDirectory() as tmp:
            sink = NovelTxtSink(
                interval=0.0,
                change_threshold=0.0,
                describer=describer,
                out_path=pathlib.Path(tmp) / "novel.md",
                no_chat=True,
                stream=open(pathlib.Path(tmp) / "stdout.txt", "w", encoding="utf-8"),
            )
            sink.open(64, 36)
            t0 = time.perf_counter()
            for grid in itertools.islice(source.frames(), 30):
                sink.write(grid)
            elapsed = time.perf_counter() - t0
            # Allow the first worker to finish so close() is clean.
            time.sleep(1.2)
            sink.close()
            sink._stream.close()

        self.assertLess(elapsed, 0.2, f"write() blocked for {elapsed:.3f}s")
        # At most one call in flight: with sleep=1s and interval=0, later beats skip.
        self.assertGreaterEqual(sink._engine.skips_busy, 1)
        # ScriptedDescriber should not have been entered re-entrantly.
        self.assertLessEqual(len(describer.calls), 2)


if __name__ == "__main__":
    unittest.main()
