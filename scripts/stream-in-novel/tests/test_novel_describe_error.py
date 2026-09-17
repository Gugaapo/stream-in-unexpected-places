"""Acceptance: DescribeError is surfaced; the sink keeps running."""

from __future__ import annotations

import io
import itertools
import pathlib
import sys
import tempfile
import time
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.describe import DescribeError, OpenAICompatDescriber  # noqa: E402
from streamkit.sinks.novel import NovelTxtSink  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402


class TestNovelDescribeError(unittest.TestCase):
    def test_openai_compat_raises_describe_error_on_dead_port(self) -> None:
        d = OpenAICompatDescriber(
            base_url="http://127.0.0.1:1/v1/",
            model="x",
            api_key="fake-key-for-test",
            timeout=0.5,
        )
        with self.assertRaises(DescribeError) as ctx:
            d.describe(system="s", user="u", image_png=b"\x89PNG\r\n\x1a\nxxxx")
        self.assertIsInstance(ctx.exception, DescribeError)

    def test_sink_survives_describe_error(self) -> None:
        class Boom:
            def describe(self, *, system, user, image_png, on_token=None):
                raise DescribeError("HTTP 503: boom", status=503, body="boom")

        with tempfile.TemporaryDirectory() as tmp:
            sink = NovelTxtSink(
                interval=0.0,
                change_threshold=0.0,
                describer=Boom(),
                out_path=pathlib.Path(tmp) / "n.md",
                no_chat=True,
                stream=io.StringIO(),
            )
            sink.open(24, 16)
            source = PatternSource("bars", width=24, height=16, fps=10)
            for grid in itertools.islice(source.frames(), 8):
                sink.write(grid)  # must not raise
                time.sleep(0.02)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not sink._engine.last_error:
                time.sleep(0.02)
            self.assertTrue(sink._engine.last_error)
            self.assertIn("error:", sink._engine.status_line().lower())
            self.assertGreaterEqual(sink.frames_written, 8)
            sink.close()


if __name__ == "__main__":
    unittest.main()
