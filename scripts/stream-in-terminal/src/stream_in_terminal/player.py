"""Playback loop: resolve the stream with streamkit, render pixel art + chat.

Everything upstream of the drawing — Twitch resolution, the ffmpeg decode pipe, the Grid, the
terminal renderer, the chat client, the ffmpeg lookup — comes from the ``streamkit`` library. What is
local to this medium is the player itself: the layout, the status line, the chat pane and recording.
"""

from __future__ import annotations

import shutil
import sys
import time
from dataclasses import dataclass

from streamkit.chat import TwitchChat, format_chat_block, prepare_chat_rows
from streamkit.ffmpeg import find_ffmpeg
from streamkit.render import (
    RenderMode,
    pixel_dimensions,
    render_frame,
    resize_rgb,
    resolve_charset,
    supports_truecolor,
)
from streamkit.sources import Source, TwitchSource
from streamkit.sources.twitch import StreamResolveError

from .record import Mp4Recorder, default_record_path
from .record_overlay import compose_record_frame, record_output_size

HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CURSOR_HOME = "\x1b[H"
CLEAR_SCREEN = "\x1b[2J"
CLEAR_EOS = "\x1b[0J"  # clear from cursor to end of screen
ALT_ENTER = "\x1b[?1049h"
ALT_LEAVE = "\x1b[?1049l"
WRAP_OFF = "\x1b[?7l"  # prevent wrap from shredding the frame
WRAP_ON = "\x1b[?7h"

DEFAULT_CHAT_LINES = 5
# Default decode grid — resampled in Python on each frame for live resize.
DECODE_WIDTH = 160
DECODE_HEIGHT = 48
DECODE_MAX = 640  # hard cap to avoid melting CPU/RAM


def parse_decode_size(value: str) -> tuple[int, int]:
    """Parse WxH (e.g. 240x72). Raises ValueError on bad input."""
    text = value.strip().lower().replace("*", "x").replace(",", "x")
    if "x" not in text:
        raise ValueError("expected WIDTHxHEIGHT (e.g. 240x72)")
    left, right = text.split("x", 1)
    if not left.isdigit() or not right.isdigit():
        raise ValueError("expected WIDTHxHEIGHT with integer parts (e.g. 240x72)")
    w, h = int(left), int(right)
    if w < 16 or h < 9:
        raise ValueError("decode size must be at least 16x9")
    if w > DECODE_MAX or h > DECODE_MAX:
        raise ValueError(f"decode size must be at most {DECODE_MAX}x{DECODE_MAX}")
    return w, h


def _enable_windows_ansi() -> None:
    """Enable VT processing on Windows consoles so ANSI escapes work."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass


@dataclass
class PlayerOptions:
    channel_or_url: str
    fps: float = 12.0
    width: int | None = None
    quality: str = "best"
    mode: RenderMode = RenderMode.COMPACT
    chars: str = "classic"
    color: bool | None = None  # None = auto
    use_alt_screen: bool = True
    chat: bool = True
    chat_lines: int = DEFAULT_CHAT_LINES
    decode_width: int = DECODE_WIDTH
    decode_height: int = DECODE_HEIGHT
    record_path: str | None = None
    record_scale: int = 8


def _layout(
    opt_width: int | None,
    chat: bool,
    chat_lines: int,
    mode: RenderMode,
) -> tuple[int, int, int]:
    """
    Returns (pixel_width, pixel_height, terminal_video_rows).

    Reserves 1 status line and optional chat rows below the video.
    """
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    cols = max(2, cols)
    if opt_width is not None:
        cols = max(2, min(opt_width, cols))

    below = 1  # status
    if chat:
        below += max(1, chat_lines)

    video_rows = max(2, rows - below)
    pixel_w, pixel_h = pixel_dimensions(cols, video_rows, mode)
    return pixel_w, pixel_h, video_rows


def _terminal_cols(opt_width: int | None) -> int:
    cols, _ = shutil.get_terminal_size(fallback=(80, 24))
    cols = max(2, cols)
    if opt_width is not None:
        cols = max(2, min(opt_width, cols))
    return cols


def _build_status_line(
    channel: str,
    mode: RenderMode,
    width: int,
    height: int,
    fps: float,
    terminal_cols: int,
    chat_client: TwitchChat | None,
) -> str:
    chat_note = ""
    if chat_client is not None:
        st = chat_client.status
        if st and st != "chat live":
            chat_note = f" | {st}"
    status = (
        f"{channel} | {mode.value} {width}x{height} @ {fps:.0f}fps{chat_note} | Ctrl+C quit"
    )
    if len(status) > terminal_cols:
        status = status[: max(1, terminal_cols - 1)] + "…"
    return status


def _render_frame(
    out,
    *,
    rgb: bytes,
    width: int,
    height: int,
    terminal_cols: int,
    mode: RenderMode,
    charset: str,
    use_color: bool,
    use_truecolor: bool,
    channel: str,
    fps: float,
    chat_client: TwitchChat | None,
    chat_lines: int,
) -> None:
    art = render_frame(
        rgb,
        width,
        height,
        mode=mode,
        chars=charset,
        color=use_color,
        truecolor=use_truecolor,
    )
    status = _build_status_line(
        channel,
        mode,
        width,
        height,
        fps,
        terminal_cols,
        chat_client,
    )

    parts = [CURSOR_HOME, art, "\n", status]
    if chat_client is not None:
        block = format_chat_block(
            chat_client.latest(),
            width=terminal_cols,
            lines=chat_lines,
            color=use_color,
            placeholder="",
        )
        parts.extend(["\n", block])
    # Wipe any leftover cells when the previous frame was larger.
    parts.append(CLEAR_EOS)
    out.write("".join(parts))
    out.flush()


def play(options: PlayerOptions) -> int:
    """Run the player until EOF, stream end, or KeyboardInterrupt. Returns exit code."""
    chat_lines = max(1, options.chat_lines)
    charset = resolve_charset(options.chars)
    if options.mode == RenderMode.ASCII:
        if options.color is False:
            use_color = False
            use_truecolor = False
        elif options.color is True:
            use_color = True
            use_truecolor = True
        else:
            use_truecolor = supports_truecolor()
            use_color = use_truecolor
    else:
        use_color = options.color is not False
        use_truecolor = options.color is True
    fps = max(1.0, min(30.0, options.fps))
    decode_w = max(16, min(DECODE_MAX, options.decode_width))
    decode_h = max(9, min(DECODE_MAX, options.decode_height))

    out = sys.stdout
    entered_alt = False
    wrap_disabled = False
    frames_seen = 0
    ffmpeg_err = b""
    chat_client: TwitchChat | None = None
    prev_layout: tuple[int, int, int] | None = None
    recorder: Mp4Recorder | None = None
    source: Source | None = None
    record_layout: tuple[int, int] | None = None
    record_terminal_cols = 0
    record_chat_lines = 0
    record_scale = max(1, options.record_scale)

    try:
        ffmpeg = find_ffmpeg()  # fail early, with advice, if ffmpeg is missing or broken
        source = TwitchSource(
            options.channel_or_url,
            width=decode_w,
            height=decode_h,
            fps=fps,
            quality=options.quality,
        )
        source.open()  # resolves the channel and starts ffmpeg; raises StreamResolveError
        channel = source.channel

        _enable_windows_ansi()
        if options.use_alt_screen and out.isatty():
            out.write(ALT_ENTER)
            entered_alt = True
        if out.isatty():
            out.write(WRAP_OFF)
            wrap_disabled = True
        out.write(HIDE_CURSOR + CLEAR_SCREEN + CURSOR_HOME)
        out.flush()

        if options.chat:
            chat_client = TwitchChat(channel, max_messages=chat_lines)
            chat_client.start()

        if options.record_path is not None:
            record_path = options.record_path or default_record_path(channel)
            record_terminal_cols = _terminal_cols(options.width)
            record_chat_lines = chat_lines if options.chat else 0
            record_pixel_w, record_pixel_h, _ = _layout(
                options.width, options.chat, chat_lines, options.mode
            )
            record_layout = (record_pixel_w, record_pixel_h)
            record_fw, record_fh = record_output_size(
                record_pixel_w,
                record_pixel_h,
                scale=record_scale,
                text_cols=record_terminal_cols,
                mode=options.mode,
                chat_lines=record_chat_lines,
            )
            recorder = Mp4Recorder(
                record_path,
                frame_width=record_fw,
                frame_height=record_fh,
                fps=fps,
                ffmpeg_path=ffmpeg,
            )
            print(
                f"recording to {record_path} ({record_fw}x{record_fh} @ {fps:.0f}fps)",
                file=sys.stderr,
            )

        frame_interval = 1.0 / fps
        next_deadline = time.perf_counter()
        for grid in source.frames():
            rgb = grid.rgb_bytes
            pixel_w, pixel_h, video_rows = _layout(
                options.width, options.chat, chat_lines, options.mode
            )
            terminal_cols, _ = shutil.get_terminal_size(fallback=(80, 24))
            if options.width is not None:
                terminal_cols = max(2, min(terminal_cols, options.width))

            # Keep display dimensions locked to the recording canvas so a
            # window resize cannot spike CPU / block the ffmpeg pipe.
            if record_layout is not None:
                pixel_w, pixel_h = record_layout
                terminal_cols = record_terminal_cols
                video_rows = (
                    pixel_h // 2 if options.mode == RenderMode.COMPACT else pixel_h
                )

            if prev_layout is not None and (pixel_w, pixel_h, video_rows) != prev_layout:
                # Full clear once when the grid changes; avoid blanking every frame.
                out.write(CLEAR_SCREEN)
                out.flush()
                next_deadline = time.perf_counter()
            prev_layout = (pixel_w, pixel_h, video_rows)

            frames_seen += 1
            now = time.perf_counter()
            if now < next_deadline:
                time.sleep(next_deadline - now)
            next_deadline = time.perf_counter() + frame_interval

            view = resize_rgb(rgb, decode_w, decode_h, pixel_w, pixel_h)
            if recorder is not None and record_layout is not None:
                rec_w, rec_h = record_layout
                chat_rows = []
                if chat_client is not None and record_chat_lines > 0:
                    chat_rows = prepare_chat_rows(
                        chat_client.latest(),
                        record_terminal_cols,
                        record_chat_lines,
                        color=use_color,
                    )
                status = _build_status_line(
                    channel,
                    options.mode,
                    rec_w,
                    rec_h,
                    fps,
                    record_terminal_cols,
                    chat_client,
                )
                frame = compose_record_frame(
                    view,
                    rec_w,
                    rec_h,
                    scale=record_scale,
                    text_cols=record_terminal_cols,
                    mode=options.mode,
                    status=status,
                    chat_rows=chat_rows,
                    chat_lines=record_chat_lines,
                )
                recorder.write_frame(frame)
            _render_frame(
                out,
                rgb=view,
                width=pixel_w,
                height=pixel_h,
                terminal_cols=terminal_cols,
                mode=options.mode,
                charset=charset,
                use_color=use_color,
                use_truecolor=use_truecolor,
                channel=channel,
                fps=fps,
                chat_client=chat_client,
                chat_lines=chat_lines,
            )

        ffmpeg_err = source.stderr()

        if frames_seen == 0:
            msg = ffmpeg_err.decode("utf-8", errors="replace").strip()
            if msg:
                print(f"error: ffmpeg produced no frames: {msg}", file=sys.stderr)
            else:
                print(
                    "error: ffmpeg produced no frames "
                    "(stream may have ended or URL expired).",
                    file=sys.stderr,
                )
            return 1
        if recorder is not None and recorder.frames_written > 0:
            print(
                f"saved {recorder.frames_written} frames to {recorder.path}",
                file=sys.stderr,
            )
        return 0
    except KeyboardInterrupt:
        if recorder is not None and recorder.frames_written > 0:
            print(
                f"saved {recorder.frames_written} frames to {recorder.path}",
                file=sys.stderr,
            )
        return 0
    except StreamResolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"error: recording failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if recorder is not None:
            recorder.close()
        if chat_client is not None:
            chat_client.stop()
        if source is not None:
            source.close()
        if out.isatty():
            if wrap_disabled:
                out.write(WRAP_ON)
            if entered_alt:
                out.write(ALT_LEAVE)
            out.write(SHOW_CURSOR)
            out.flush()
