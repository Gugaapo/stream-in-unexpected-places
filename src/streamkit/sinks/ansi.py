"""The terminal sink: half-block / colored-block / ASCII pixel art, exactly as live-in-terminal.

Kept byte-identical to the historical renderer on purpose — see tests/test_ansi_regression.py.
"""

from __future__ import annotations

import shutil
import sys

from ..grid import Grid
from ..render import (
    RenderMode,
    pixel_dimensions,
    render_frame,
    resolve_charset,
    resolve_render_mode,
    supports_truecolor,
)
from ..sink import register

CURSOR_HOME = "\x1b[H"
CLEAR_EOS = "\x1b[0J"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
RESET = "\x1b[0m"


@register("ansi")
class AnsiSink:
    """Draw each frame as ANSI pixel art on a terminal.

    With ``pixel_size`` set, the terminal is not consulted at all (deterministic; used by tests
    and by any caller that already knows the geometry).
    """

    def __init__(
        self,
        *,
        mode: str = "compact",
        charset: str | None = None,
        color: bool = True,
        truecolor: bool | None = None,
        cols: int | None = None,
        video_rows: int | None = None,
        pixel_size: tuple[int, int] | None = None,
        stream=None,
        status: bool = True,
        label: str = "",
        fps: float = 12.0,
    ) -> None:
        self.mode: RenderMode = resolve_render_mode(mode)
        self.charset = resolve_charset(charset)
        self.color = bool(color)
        self.truecolor = supports_truecolor() if truecolor is None else bool(truecolor)
        self._cols = cols
        self._video_rows = video_rows
        self._pixel_size = pixel_size
        self._stream = stream if stream is not None else sys.stdout
        self.status = status
        self.label = label
        self.fps = float(fps)

        self.pixel_width = 0
        self.pixel_height = 0
        self.cols = 0
        self.frames_written = 0

    # ----- geometry ---------------------------------------------------------
    def open(self, width: int, height: int) -> None:
        if self._pixel_size is not None:
            self.cols = int(self._pixel_size[0])
            self.pixel_width, self.pixel_height = int(self._pixel_size[0]), int(self._pixel_size[1])
        else:
            term_cols, term_rows = shutil.get_terminal_size(fallback=(80, 24))
            cols = max(2, int(self._cols)) if self._cols else max(2, term_cols)
            if self._cols:
                cols = min(cols, max(2, term_cols))
            video_rows = int(self._video_rows) if self._video_rows else max(2, term_rows - 1)
            self.pixel_width, self.pixel_height = pixel_dimensions(cols, video_rows, self.mode)
            self.cols = cols

    def art_for(self, grid: Grid) -> str:
        """The ANSI art for one frame — the unit the regression test compares."""
        if self.pixel_width < 1 or self.pixel_height < 1:
            raise RuntimeError("sink is not opened")
        resized = grid.resize(self.pixel_width, self.pixel_height, method="nearest")
        return render_frame(
            resized.rgb_bytes,
            resized.width,
            resized.height,
            mode=self.mode,
            chars=self.charset,
            color=self.color,
            truecolor=self.truecolor,
        )

    def status_line(self) -> str:
        text = (
            f"{self.label} | {self.mode.value} {self.pixel_width}x{self.pixel_height} "
            f"@ {self.fps:.0f}fps | Ctrl+C quit"
        )
        if self.cols and len(text) > self.cols:
            text = text[: max(1, self.cols - 1)] + "…"
        return text

    # ----- Sink protocol ----------------------------------------------------
    def write(self, grid: Grid) -> None:
        art = self.art_for(grid)
        chunks = [CURSOR_HOME, art]
        if self.status:
            chunks.extend(["\n", self.status_line()])
        chunks.append(CLEAR_EOS)
        self._stream.write("".join(chunks))
        self._stream.flush()
        self.frames_written += 1

    def close(self) -> None:
        try:
            self._stream.write(SHOW_CURSOR + RESET)
            self._stream.flush()
        except (OSError, ValueError):
            pass
