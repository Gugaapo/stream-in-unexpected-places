"""Novel sinks: the stream narrates itself as prose.

``novel`` — ANSI live view (upper prose pane + lower chat pane).
``novel_txt`` — plain text to a stream/file (pipe-friendly / CI-testable).

``write(grid)`` never blocks on the network: a single background worker talks to
the describer and appends the transcript. If a request is in flight when the next
interval elapses, the beat is skipped (no queue).
"""

from __future__ import annotations

import io
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from streamkit.chat import TwitchChat, format_chat_block, prepare_chat_rows
from streamkit.describe import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DescribeError,
    Describer,
    NullDescriber,
    OpenAICompatDescriber,
    ScriptedDescriber,
    resolve_api_key,
)
from streamkit.grid import Grid
from streamkit.render.png import png_bytes
from streamkit.sink import register

from ..novel import StoryState, build_prompt, should_describe

ALT_ENTER = "\x1b[?1049h"
ALT_LEAVE = "\x1b[?1049l"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CURSOR_HOME = "\x1b[H"
CLEAR_EOS = "\x1b[0J"
RESET = "\x1b[0m"

SCRIPTED_DEFAULTS = [
    "Bars of colour marched across the void like a parade with nowhere to go.",
    "Someone in chat whispered a name, and the parade hesitated - then marched on.",
    "The story found its rhythm in the silence between one frame and the next.",
    "A new hue bloomed at the edge, and the chapter turned a quiet corner.",
]


def _default_out_path(channel: str | None) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d")
    name = (channel or "stream").lower()
    return Path("out") / "novel" / f"{name}-{stamp}.md"


def _wrap_words(text: str, width: int) -> list[str]:
    width = max(8, int(width))
    lines: list[str] = []
    for para in (text or "").splitlines() or [""]:
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if len(cur) + 1 + len(w) <= width:
                cur = f"{cur} {w}"
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


class _NovelEngine:
    """Shared worker / gate / transcript for novel and novel_txt."""

    def __init__(
        self,
        *,
        interval: float = 15.0,
        change_threshold: float = 1.5,
        style: str = "dumb",
        lang: str = "pt-BR",
        no_chat: bool = False,
        chat_channel: str | None = None,
        out_path: str | Path | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        describer: str | Describer | None = "openai",
        color: bool = True,
        label: str = "",
    ) -> None:
        self.interval = max(0.0, float(interval))
        self.change_threshold = float(change_threshold)
        self.style = style or "dumb"
        self.lang = lang or "pt-BR"
        self.no_chat = bool(no_chat)
        self._chat_channel = None if no_chat else chat_channel
        self.color = bool(color)
        self.label = label or (chat_channel or "stream")

        self.out_path = Path(out_path) if out_path else _default_out_path(chat_channel)
        self.state = StoryState()
        self.frames_written = 0
        self.calls_made = 0
        self.skips_busy = 0
        self.skips_gate = 0
        self.last_error = ""
        self._status_extra = ""

        self._chat: TwitchChat | None = None
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._busy = False
        self._closed = False
        self._opened = False
        self._header_written = False

        self._latest: Grid | None = None
        self._last_described: Grid | None = None
        self._last_chat_count = 0
        self._last_call_at = 0.0
        self._next_due = 0.0
        self._streaming_text = ""
        self._started_at = 0.0

        self.describer: Describer = self._build_describer(
            describer, base_url=base_url, model=model, api_key=api_key
        )

    def _build_describer(
        self,
        describer: str | Describer | None,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
    ) -> Describer:
        if describer is not None and not isinstance(describer, str) and callable(
            getattr(describer, "describe", None)
        ):
            return describer  # type: ignore[return-value]
        name = (describer or "openai").strip().lower() if isinstance(describer, str) else "openai"
        if name in ("null", "none"):
            return NullDescriber()
        if name in ("scripted", "script"):
            return ScriptedDescriber(SCRIPTED_DEFAULTS)
        key = resolve_api_key(api_key)
        if not key and name in ("openai", "auto"):
            # No key → degrade to Null so the sink still runs.
            self._status_extra = "no describer (missing API key)"
            return NullDescriber()
        return OpenAICompatDescriber(base_url=base_url, model=model, api_key=key)

    # ----- lifecycle --------------------------------------------------------
    def open(self, width: int, height: int) -> None:
        self._opened = True
        self._closed = False
        self._started_at = time.monotonic()
        self._next_due = self._started_at  # first beat ASAP
        if self._chat_channel:
            self._chat = TwitchChat(self._chat_channel, max_messages=24)
            self._chat.start()
        self._ensure_header()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Wait briefly for an in-flight call so the last paragraph can land.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with self._lock:
                if not self._busy:
                    break
            time.sleep(0.05)
        if self._chat is not None:
            self._chat.stop()
            self._chat = None

    def _ensure_header(self) -> None:
        if self._header_written:
            return
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.out_path.exists() and self.out_path.stat().st_size > 0
        with self.out_path.open("a", encoding="utf-8") as fh:
            if not exists:
                stamp = datetime.now().isoformat(timespec="seconds")
                fh.write(
                    f"# novel - {self.label}\n"
                    f"style: {self.style} | lang: {self.lang} | started: {stamp}\n\n"
                )
            else:
                stamp = datetime.now().isoformat(timespec="seconds")
                fh.write(f"\n---\n# resumed {stamp} | style: {self.style} | lang: {self.lang}\n\n")
        self._header_written = True

    def _append_transcript(self, paragraph: str) -> None:
        text = (paragraph or "").strip()
        if not text:
            return
        self._ensure_header()
        with self.out_path.open("a", encoding="utf-8") as fh:
            fh.write(text.replace("\n", " ").strip() + "\n")

    def _chat_pairs(self) -> list[tuple[str, str]]:
        if self._chat is None:
            return []
        return [(m.user, m.text) for m in self._chat.latest()]

    def _chat_status(self) -> str:
        if self.no_chat:
            return "chat off"
        if self._chat is None:
            return "no chat"
        return self._chat.status

    # ----- write path (non-blocking) ----------------------------------------
    def on_frame(self, grid: Grid) -> None:
        self.frames_written += 1
        with self._lock:
            self._latest = grid.copy()
            busy = self._busy
            due = time.monotonic() >= self._next_due

        if not due:
            return
        if busy:
            self.skips_busy += 1
            with self._lock:
                self._next_due = time.monotonic() + self.interval
            return

        chat = self._chat_pairs()
        with self._lock:
            prev = self._last_described
            last_n = self._last_chat_count
        if not should_describe(prev, grid, chat, last_n, self.change_threshold):
            self.skips_gate += 1
            with self._lock:
                self._next_due = time.monotonic() + self.interval
            return

        self._spawn_worker(grid.copy(), chat)

    def _spawn_worker(self, grid: Grid, chat: list[tuple[str, str]]) -> None:
        with self._lock:
            if self._busy or self._closed:
                return
            self._busy = True
            self._next_due = time.monotonic() + self.interval
            self._streaming_text = ""

        def run() -> None:
            try:
                self._describe_once(grid, chat)
            finally:
                with self._lock:
                    self._busy = False

        t = threading.Thread(target=run, name="novel-describer", daemon=True)
        self._worker = t
        t.start()

    def _describe_once(self, grid: Grid, chat: list[tuple[str, str]]) -> None:
        if isinstance(self.describer, NullDescriber):
            with self._lock:
                self._status_extra = self._status_extra or "no describer"
                self._last_described = grid
                self._last_chat_count = len(chat)
            return

        system, user = build_prompt(
            self.state,
            chat,
            self.style,
            self.lang,
            self._chat_channel or self.label,
        )
        try:
            png = png_bytes(grid.rgb_bytes, grid.width, grid.height)

            def on_token(piece: str) -> None:
                with self._lock:
                    self._streaming_text += piece

            text = self.describer.describe(
                system=system, user=user, image_png=png, on_token=on_token
            )
        except DescribeError as exc:
            with self._lock:
                self.last_error = str(exc)[:160]
                # Rate limits need a long cool-down; retrying every 15s just burns quota.
                cooldown = 60.0 if getattr(exc, "status", None) == 429 else self.interval
                self._next_due = time.monotonic() + cooldown
                if getattr(exc, "status", None) == 429:
                    self._status_extra = f"rate-limited (429) — cooling {cooldown:.0f}s"
                else:
                    self._status_extra = f"error: {self.last_error}"
            return
        except Exception as exc:  # noqa: BLE001 — keep the frame loop alive
            with self._lock:
                self.last_error = f"{type(exc).__name__}: {exc}"[:160]
                self._status_extra = f"error: {self.last_error}"
            return

        text = (text or "").strip()
        with self._lock:
            self.calls_made += 1
            self._last_call_at = time.monotonic()
            self._last_described = grid
            self._last_chat_count = len(chat)
            self._streaming_text = text
            self.last_error = ""
            if not isinstance(self.describer, NullDescriber):
                self._status_extra = ""
        if text:
            self.state.add(text)
            self._append_transcript(text)

    def seconds_to_next(self) -> float:
        with self._lock:
            return max(0.0, self._next_due - time.monotonic())

    def in_flight(self) -> bool:
        with self._lock:
            return self._busy

    def prose_text(self) -> str:
        with self._lock:
            live = self._streaming_text.strip()
        paras = self.state.paragraphs
        if live and (not paras or paras[-1] != live):
            # Show committed paragraphs + current stream.
            body = "\n\n".join(paras)
            return f"{body}\n\n{live}".strip() if body else live
        return "\n\n".join(paras)

    def status_line(self) -> str:
        bits = [
            f"novel/{self.style}",
            self.lang,
            f"calls={self.calls_made}",
            f"next={self.seconds_to_next():.0f}s",
            self._chat_status(),
        ]
        if self.in_flight():
            bits.append("describing…")
        if self._status_extra:
            bits.append(self._status_extra)
        return " | ".join(bits)


@register("novel_txt")
class NovelTxtSink:
    """Plain-text novel sink — stdout/file, no ANSI escapes."""

    def __init__(
        self,
        *,
        interval: float = 15.0,
        change_threshold: float = 1.5,
        style: str = "dumb",
        lang: str = "pt-BR",
        no_chat: bool = False,
        chat_channel: str | None = None,
        out_path: str | Path | None = None,
        path: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        describer: str | Describer | None = "openai",
        color: bool = True,
        label: str = "",
        stream: TextIO | None = None,
        **_kwargs,
    ) -> None:
        out = out_path or path
        self._engine = _NovelEngine(
            interval=interval,
            change_threshold=change_threshold,
            style=style,
            lang=lang,
            no_chat=no_chat,
            chat_channel=chat_channel,
            out_path=out,
            base_url=base_url,
            model=model,
            api_key=api_key,
            describer=describer,
            color=color,
            label=label,
        )
        self._stream = stream if stream is not None else sys.stdout
        self._last_printed = 0
        self.frames_written = 0

    @property
    def path(self) -> Path:
        return self._engine.out_path

    @property
    def out_path(self) -> Path:
        return self._engine.out_path

    def open(self, width: int, height: int) -> None:
        self._engine.open(width, height)

    def write(self, grid: Grid) -> None:
        self._engine.on_frame(grid)
        self.frames_written = self._engine.frames_written
        # Print newly committed paragraphs only.
        paras = self._engine.state.paragraphs
        while self._last_printed < len(paras):
            line = paras[self._last_printed]
            self._stream.write(line + "\n")
            self._stream.flush()
            self._last_printed += 1

    def close(self) -> None:
        self._engine.close()
        # Flush any final paragraph that landed during close wait.
        paras = self._engine.state.paragraphs
        while self._last_printed < len(paras):
            self._stream.write(paras[self._last_printed] + "\n")
            self._stream.flush()
            self._last_printed += 1


@register("novel")
class NovelAnsiSink:
    """ANSI live novel: prose pane + chat pane + status line."""

    def __init__(
        self,
        *,
        interval: float = 15.0,
        change_threshold: float = 1.5,
        style: str = "dumb",
        lang: str = "pt-BR",
        no_chat: bool = False,
        chat_channel: str | None = None,
        out_path: str | Path | None = None,
        path: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        describer: str | Describer | None = "openai",
        color: bool = True,
        label: str = "",
        stream: TextIO | None = None,
        **_kwargs,
    ) -> None:
        out = out_path or path
        self._engine = _NovelEngine(
            interval=interval,
            change_threshold=change_threshold,
            style=style,
            lang=lang,
            no_chat=no_chat,
            chat_channel=chat_channel,
            out_path=out,
            base_url=base_url,
            model=model,
            api_key=api_key,
            describer=describer,
            color=color,
            label=label,
        )
        self._stream = stream if stream is not None else sys.stdout
        self.color = bool(color)
        self._alt_on = False
        self.frames_written = 0

    @property
    def path(self) -> Path:
        return self._engine.out_path

    def open(self, width: int, height: int) -> None:
        self._engine.open(width, height)
        self._stream.write(ALT_ENTER + HIDE_CURSOR)
        self._stream.flush()
        self._alt_on = True

    def write(self, grid: Grid) -> None:
        self._engine.on_frame(grid)
        self.frames_written = self._engine.frames_written
        self._render()

    def close(self) -> None:
        self._engine.close()
        if self._alt_on:
            self._stream.write(SHOW_CURSOR + ALT_LEAVE + RESET)
            self._stream.flush()
            self._alt_on = False

    def _render(self) -> None:
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        cols = max(40, cols)
        rows = max(10, rows)
        chat_lines = 4
        status_rows = 1
        sep_rows = 1
        prose_rows = max(3, rows - chat_lines - status_rows - sep_rows - 1)

        prose = self._engine.prose_text()
        if not prose and isinstance(self._engine.describer, NullDescriber):
            prose = "(no describer — set DEEPSEEK_API_KEY or --novel-describer scripted)"
        wrapped = _wrap_words(prose, cols - 2)
        # Bottom-anchor: keep the last prose_rows lines.
        view = wrapped[-prose_rows:]
        while len(view) < prose_rows:
            view.insert(0, "")

        h_char = "-" if not self.color else "─"
        sep = h_char * cols

        messages = self._engine._chat.latest() if self._engine._chat else []
        chat_block = format_chat_block(
            messages, cols, lines=chat_lines, color=self.color, placeholder=""
        )
        # Also touch prepare_chat_rows so the API stays exercised / available.
        _ = prepare_chat_rows(messages, cols, lines=chat_lines, color=self.color)

        status = self._engine.status_line()
        if len(status) > cols:
            status = status[: cols - 1] + "…"

        buf = io.StringIO()
        buf.write(CURSOR_HOME + CLEAR_EOS)
        for line in view:
            buf.write(line[:cols].ljust(cols) + "\n")
        buf.write(sep[:cols] + "\n")
        buf.write(chat_block)
        if not chat_block.endswith("\n"):
            buf.write("\n")
        buf.write(status[:cols])
        self._stream.write(buf.getvalue())
        self._stream.flush()
