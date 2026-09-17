"""Acceptance: transcript append + ANSI save/restore on close."""

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

from streamkit.describe import ScriptedDescriber  # noqa: E402
from stream_in_novel.sinks.novel import ALT_ENTER, ALT_LEAVE, HIDE_CURSOR, SHOW_CURSOR, NovelAnsiSink, NovelTxtSink  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402


class TestNovelTranscript(unittest.TestCase):
    def test_paragraphs_land_in_order_with_header_and_append(self) -> None:
        paras = [
            "First paragraph of the night.",
            "Second paragraph follows quietly.",
            "Third paragraph closes the beat.",
        ]
        describer = ScriptedDescriber(paras, sleep=0.0)
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "omeiaum.md"
            stdout = io.StringIO()
            sink = NovelTxtSink(
                interval=0.0,
                change_threshold=0.0,
                describer=describer,
                out_path=out,
                no_chat=True,
                label="omeiaum",
                style="noir",
                lang="en",
                stream=stdout,
            )
            sink.open(32, 18)
            source = PatternSource("noise", width=32, height=18, fps=5, seed=1)
            for grid in itertools.islice(source.frames(), 6):
                sink.write(grid)
                time.sleep(0.05)
            sink.close()
            text = out.read_text(encoding="utf-8")
            self.assertIn("# novel - omeiaum", text)
            self.assertIn("style: noir", text)
            for p in paras:
                self.assertIn(p, text)
            # Order preserved.
            positions = [text.index(p) for p in paras]
            self.assertEqual(positions, sorted(positions))

            # Second run appends rather than truncates.
            describer2 = ScriptedDescriber(["Fourth after reopen."], sleep=0.0)
            sink2 = NovelTxtSink(
                interval=0.0,
                change_threshold=0.0,
                describer=describer2,
                out_path=out,
                no_chat=True,
                label="omeiaum",
                stream=io.StringIO(),
            )
            sink2.open(32, 18)
            g = next(PatternSource("sweep", width=32, height=18, fps=5).frames())
            sink2.write(g)
            time.sleep(0.05)
            sink2.close()
            sink2.close()  # idempotent
            text2 = out.read_text(encoding="utf-8")
            self.assertIn("First paragraph of the night.", text2)
            self.assertIn("Fourth after reopen.", text2)
            self.assertIn("resumed", text2)

    def test_ansi_restores_terminal(self) -> None:
        buf = io.StringIO()
        sink = NovelAnsiSink(
            interval=60.0,
            describer=ScriptedDescriber(["x"], sleep=0.0),
            out_path=pathlib.Path(tempfile.mkdtemp()) / "t.md",
            no_chat=True,
            stream=buf,
        )
        sink.open(40, 24)
        opened = buf.getvalue()
        self.assertIn(ALT_ENTER, opened)
        self.assertIn(HIDE_CURSOR, opened)
        g = next(PatternSource("bars", width=40, height=24, fps=1).frames())
        sink.write(g)
        sink.close()
        sink.close()
        body = buf.getvalue()
        # save (alt enter) then restore (show cursor + alt leave), in that order.
        i_enter = body.index(ALT_ENTER)
        i_show = body.index(SHOW_CURSOR)
        i_leave = body.index(ALT_LEAVE)
        self.assertLess(i_enter, i_show)
        self.assertLess(i_show, i_leave)


if __name__ == "__main__":
    unittest.main()
