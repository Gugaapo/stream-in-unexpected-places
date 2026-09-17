"""Fidelity check: the ansi sink must render byte-identically to stream-in-terminal's renderer.

This is the strongest evidence that the port is faithful. It reads the sibling script
(`scripts/stream-in-terminal`) directly and skips (rather than fails) if it is not present.
"""

from __future__ import annotations

import importlib
import io
import itertools
import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SIBLING_SRC = pathlib.Path(__file__).resolve().parents[2] / "stream-in-terminal" / "src"
HAVE_SIBLING = (SIBLING_SRC / "stream_in_terminal" / "render.py").is_file()

from streamkit.sinks.ansi import AnsiSink  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402

PIXEL_SIZE = (80, 48)
DECODE_SIZE = (40, 24)


def old_renderer():
    if str(SIBLING_SRC) not in sys.path:
        sys.path.insert(0, str(SIBLING_SRC))
    return importlib.import_module("stream_in_terminal.render")


@unittest.skipUnless(HAVE_SIBLING, "stream-in-terminal sibling script not present")
class TestAnsiFidelity(unittest.TestCase):
    def _grids(self, n: int = 3):
        source = PatternSource("square", width=DECODE_SIZE[0], height=DECODE_SIZE[1], fps=6)
        return list(itertools.islice(source.frames(), n))

    def _new_path(self, grid, *, mode: str) -> str:
        sink = AnsiSink(
            mode=mode,
            color=True,
            truecolor=False,
            pixel_size=PIXEL_SIZE,
            stream=io.StringIO(),
            status=False,
        )
        sink.open(DECODE_SIZE[0], DECODE_SIZE[1])
        return sink.art_for(grid)

    def _old_path(self, grid, *, mode: str) -> str:
        old = old_renderer()
        resized = old.resize_rgb(
            grid.rgb_bytes, grid.width, grid.height, PIXEL_SIZE[0], PIXEL_SIZE[1]
        )
        return old.render_frame(
            resized,
            PIXEL_SIZE[0],
            PIXEL_SIZE[1],
            mode=old.RenderMode(mode),
            chars=old.DEFAULT_CHARS,
            color=True,
            truecolor=False,
        )

    def test_all_three_modes_match_for_every_frame(self) -> None:
        for grid in self._grids():
            for mode in ("compact", "blocks", "ascii"):
                with self.subTest(index=grid.index, mode=mode):
                    self.assertEqual(self._new_path(grid, mode=mode), self._old_path(grid, mode=mode))

    def test_no_color_grayscale_matches(self) -> None:
        old = old_renderer()
        for grid in self._grids(n=2):
            resized = old.resize_rgb(
                grid.rgb_bytes, grid.width, grid.height, PIXEL_SIZE[0], PIXEL_SIZE[1]
            )
            expected = old.render_frame(
                resized,
                PIXEL_SIZE[0],
                PIXEL_SIZE[1],
                mode=old.RenderMode.COMPACT,
                chars=old.DEFAULT_CHARS,
                color=False,
                truecolor=False,
            )
            sink = AnsiSink(
                mode="compact",
                color=False,
                truecolor=False,
                pixel_size=PIXEL_SIZE,
                stream=io.StringIO(),
                status=False,
            )
            sink.open(DECODE_SIZE[0], DECODE_SIZE[1])
            self.assertEqual(sink.art_for(grid), expected)


class TestAnsiSinkBehaviour(unittest.TestCase):
    def test_write_emits_art_status_and_clear(self) -> None:
        stream = io.StringIO()
        sink = AnsiSink(pixel_size=(16, 8), stream=stream, status=True, label="pattern:bars", fps=4)
        sink.open(8, 4)
        sink.write(next(PatternSource("bars", width=8, height=4).frames()))
        out = stream.getvalue()
        self.assertIn("pattern:bars", out)
        self.assertIn("\x1b[H", out)
        self.assertTrue(out.endswith("\x1b[0J"))
        self.assertEqual(sink.frames_written, 1)

    def test_art_is_one_line_per_two_pixel_rows_in_compact_mode(self) -> None:
        sink = AnsiSink(pixel_size=(16, 8), stream=io.StringIO(), status=False)
        sink.open(8, 4)
        art = sink.art_for(next(PatternSource("bars", width=8, height=4).frames()))
        self.assertEqual(len(art.split("\n")), 4)  # 8 pixel rows / 2


if __name__ == "__main__":
    unittest.main()
