"""Convert RGB24 frames to terminal pixel art (half-blocks or colored blocks)."""

from __future__ import annotations

from enum import Enum

TOP_HALF = "\u2580"  # ▀

DEFAULT_CHARS = " .:-=+*#%@"
BLOCKS_CHARS = " ░▒▓█"


class RenderMode(str, Enum):
    COMPACT = "compact"
    BLOCKS = "blocks"
    ASCII = "ascii"


def supports_truecolor() -> bool:
    import os
    import sys

    if not sys.stdout.isatty():
        return False
    colorterm = (os.environ.get("COLORTERM") or "").lower()
    if colorterm in {"truecolor", "24bit"}:
        return True
    if os.name == "nt":
        return bool(
            os.environ.get("WT_SESSION")
            or os.environ.get("TERM_PROGRAM")
            or (os.environ.get("TERM") or "").lower() in {"xterm-256color", "xterm-truecolor"}
        )
    term = (os.environ.get("TERM") or "").lower()
    return "truecolor" in term or "256color" in term or term in {"xterm-kitty", "alacritty"}


def _luminance(r: int, g: int, b: int) -> float:
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def rgb_to_256(r: int, g: int, b: int) -> int:
    """Map an sRGB triplet to the xterm 256-color palette."""
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return round((r - 8) / 247 * 24) + 232
    return (
        16
        + 36 * round(r / 255 * 5)
        + 6 * round(g / 255 * 5)
        + round(b / 255 * 5)
    )


def resize_rgb(rgb: bytes, src_w: int, src_h: int, dst_w: int, dst_h: int) -> bytes:
    """Nearest-neighbor resize of an RGB24 buffer."""
    if src_w < 1 or src_h < 1 or dst_w < 1 or dst_h < 1:
        raise ValueError("dimensions must be >= 1")
    if src_w == dst_w and src_h == dst_h:
        return rgb
    expected = src_w * src_h * 3
    if len(rgb) < expected:
        raise ValueError("rgb buffer shorter than src dimensions")

    out = bytearray(dst_w * dst_h * 3)
    src_row_bytes = src_w * 3
    dst_row_bytes = dst_w * 3
    # Precompute x source indices for the row.
    x_src = [(x * src_w) // dst_w for x in range(dst_w)]
    for y in range(dst_h):
        sy = (y * src_h) // dst_h
        src_row = memoryview(rgb)[sy * src_row_bytes : (sy + 1) * src_row_bytes]
        dst = y * dst_row_bytes
        for x, sx in enumerate(x_src):
            si = sx * 3
            di = dst + x * 3
            out[di] = src_row[si]
            out[di + 1] = src_row[si + 1]
            out[di + 2] = src_row[si + 2]
    return bytes(out)


def _fg_code(r: int, g: int, b: int, *, color: bool, truecolor: bool) -> str:
    if not color:
        lum = int(_luminance(r, g, b) * 255)
        return f"38;5;{rgb_to_256(lum, lum, lum)}"
    if truecolor:
        return f"38;2;{r};{g};{b}"
    return f"38;5;{rgb_to_256(r, g, b)}"


def _bg_code(r: int, g: int, b: int, *, color: bool, truecolor: bool) -> str:
    if not color:
        lum = int(_luminance(r, g, b) * 255)
        return f"48;5;{rgb_to_256(lum, lum, lum)}"
    if truecolor:
        return f"48;2;{r};{g};{b}"
    return f"48;5;{rgb_to_256(r, g, b)}"


def _flush_compact_run(parts: list[str], fg: str, bg: str, text: str) -> None:
    if text:
        parts.append(f"\x1b[{fg};{bg}m{text}")


def frame_to_compact(
    rgb: bytes,
    width: int,
    height: int,
    *,
    color: bool = True,
    truecolor: bool = False,
) -> str:
    """
    Render with Unicode half-blocks (▀), two pixel rows per terminal row.

    Matches the compact style from pokemon-terminal-art (256-color ANSI).
    """
    reset = "\x1b[0m"
    lines: list[str] = []
    row_bytes = width * 3

    for y in range(0, height, 2):
        parts: list[str] = []
        run_fg = ""
        run_bg = ""
        run_text = ""
        top_base = y * row_bytes
        bot_base = top_base + row_bytes if y + 1 < height else top_base

        for x in range(width):
            ti = top_base + x * 3
            bi = bot_base + x * 3
            r1, g1, b1 = rgb[ti], rgb[ti + 1], rgb[ti + 2]
            r2, g2, b2 = rgb[bi], rgb[bi + 1], rgb[bi + 2]

            if color:
                fg = _fg_code(r1, g1, b1, color=True, truecolor=truecolor)
                bg = _bg_code(r2, g2, b2, color=True, truecolor=truecolor)
                if fg == run_fg and bg == run_bg:
                    run_text += TOP_HALF
                else:
                    _flush_compact_run(parts, run_fg, run_bg, run_text)
                    run_fg, run_bg, run_text = fg, bg, TOP_HALF
            else:
                lum = (_luminance(r1, g1, b1) + _luminance(r2, g2, b2)) * 0.5
                idx = min(len(BLOCKS_CHARS) - 1, int(lum * (len(BLOCKS_CHARS) - 1) + 0.5))
                parts.append(BLOCKS_CHARS[idx])

        if color:
            _flush_compact_run(parts, run_fg, run_bg, run_text)
            lines.append("".join(parts) + reset)
        else:
            lines.append("".join(parts))

    return "\n".join(lines)


def frame_to_blocks(
    rgb: bytes,
    width: int,
    height: int,
    *,
    color: bool = True,
    truecolor: bool = False,
) -> str:
    """
    Render with two colored spaces per pixel (background ANSI color).

    Matches the normal style from pokemon-terminal-art.
    """
    reset = "\x1b[0m"
    lines: list[str] = []
    idx = 0

    for _y in range(height):
        parts: list[str] = []
        run_bg = ""
        run_text = ""

        for _x in range(width):
            r = rgb[idx]
            g = rgb[idx + 1]
            b = rgb[idx + 2]
            idx += 3

            if color:
                bg = _bg_code(r, g, b, color=True, truecolor=truecolor)
                cell = "  "
                if bg == run_bg:
                    run_text += cell
                else:
                    if run_text:
                        parts.append(f"\x1b[{run_bg}m{run_text}")
                    run_bg, run_text = bg, cell
            else:
                lum = _luminance(r, g, b)
                ch_idx = min(len(BLOCKS_CHARS) - 1, int(lum * (len(BLOCKS_CHARS) - 1) + 0.5))
                parts.append(BLOCKS_CHARS[ch_idx] * 2)

        if color:
            if run_text:
                parts.append(f"\x1b[{run_bg}m{run_text}")
            lines.append("".join(parts) + reset)
        else:
            lines.append("".join(parts))

    return "\n".join(lines)


def frame_to_ascii(
    rgb: bytes,
    width: int,
    height: int,
    chars: str = DEFAULT_CHARS,
    color: bool = True,
) -> str:
    """Map one RGB24 frame to a multi-line ASCII string (legacy mode)."""
    if len(chars) < 2:
        chars = DEFAULT_CHARS
    n = len(chars) - 1
    lines: list[str] = []
    idx = 0
    reset = "\x1b[0m" if color else ""

    for _y in range(height):
        parts: list[str] = []
        for _x in range(width):
            r = rgb[idx]
            g = rgb[idx + 1]
            b = rgb[idx + 2]
            idx += 3
            lum = _luminance(r, g, b)
            ch = chars[min(n, int(lum * n + 0.5))]
            if color:
                parts.append(f"\x1b[38;2;{r};{g};{b}m{ch}")
            else:
                parts.append(ch)
        line = "".join(parts)
        if color:
            line += reset
        lines.append(line)

    return "\n".join(lines)


def render_frame(
    rgb: bytes,
    width: int,
    height: int,
    *,
    mode: RenderMode,
    chars: str = DEFAULT_CHARS,
    color: bool = True,
    truecolor: bool = False,
) -> str:
    if mode == RenderMode.COMPACT:
        return frame_to_compact(rgb, width, height, color=color, truecolor=truecolor)
    if mode == RenderMode.BLOCKS:
        return frame_to_blocks(rgb, width, height, color=color, truecolor=truecolor)
    use_tc = truecolor if color else False
    return frame_to_ascii(rgb, width, height, chars=chars, color=use_tc)


def resolve_render_mode(name: str | None) -> RenderMode:
    if not name:
        return RenderMode.COMPACT
    key = name.strip().lower()
    for mode in RenderMode:
        if key == mode.value:
            return mode
    raise ValueError(f"unknown render mode {name!r} (use compact, blocks, or ascii)")


def resolve_charset(name: str | None) -> str:
    if not name or name.lower() in {"classic", "default"}:
        return DEFAULT_CHARS
    if name.lower() in {"blocks", "block"}:
        return BLOCKS_CHARS
    return name


def pixel_dimensions(
    terminal_cols: int,
    terminal_video_rows: int,
    mode: RenderMode,
) -> tuple[int, int]:
    """Map terminal size to RGB buffer width/height for the given render mode."""
    if mode == RenderMode.COMPACT:
        return terminal_cols, terminal_video_rows * 2
    if mode == RenderMode.BLOCKS:
        return max(1, terminal_cols // 2), terminal_video_rows
    return terminal_cols, terminal_video_rows
