"""Compose terminal video + status + chat into RGB frames for recording."""

from __future__ import annotations

import base64
import zlib

from stream_in_terminal.chat import ChatRow
from stream_in_terminal.record import upscale_rgb
from stream_in_terminal.render import RenderMode

# Public-domain 8x8 VGA font (font8x8_basic, Daniel Hepper / IBM VGA).
_FONT_BLOB = (
    "eNrtUk2L3DAMfcXg7EHM3BYXgnPbUwsuBhOYEPc0p/6IBYNzWMge5rADKeSnb5+cpR//oUocRbL1JD0L+C8qbpq"
    "cg0NKh53SzidBZuPDIECJTmpBn/r1EldYa444sdaKA5fjP1Cn96lyQySLfICLbiD/TsaN58DT5hPmcttelxly"
    "EkqGj6G38dAheoxTinu4I5shqN1bM0TqHAlAHE9DbX7m4E4N+69lNYvW19Lz5b9mVnwnEObfts14CAFyjMi1zr"
    "VmTNUYUycMqdaaBuzXR/943Q9tz23/Vn8itrAIr+WLxz2wTNaz1ORTXXAmPde6o7zt+0spKMvrdivKYykl9S2"
    "fJR7Tx4sfm61xPnanUfv8euDGJvnQXsDol/2NeAQhFpqX5/byzf1gPm9VPLT58Pwd3ql4POjhP/IujRsVH2be"
    "a2ct+7+oHY3yH+imX+1Mnvpkz1ovsCrjQ2fTWlmv4NTqDDgI6KwSsDSv+oGoBFAP2kHDU56AizJw/sC7015rw"
    "2+DhweZRb5ojRq2HtrrYLH/XYeVBLSWYquHl/xZnjJGkU5khNOp5lKDLqyXf+f+FwzibCk="
)
_FONT_BYTES = zlib.decompress(base64.b64decode(_FONT_BLOB))

OVERLAY_BG = (16, 16, 16)
STATUS_COLOR = (180, 180, 180)
TEXT_COLOR = (220, 220, 220)


def record_output_size(
    art_w: int,
    art_h: int,
    *,
    scale: int,
    text_cols: int,
    mode: RenderMode,
    chat_lines: int = 0,
) -> tuple[int, int]:
    """Return (frame_width, frame_height) for a composed recording frame."""
    video_w, video_h = _video_output_size(art_w, art_h, scale, mode)
    frame_w = max(video_w, text_cols * scale)
    overlay_rows = 1 + max(0, chat_lines)  # status + chat
    frame_h = video_h + overlay_rows * scale
    return frame_w, frame_h


def compose_record_frame(
    art_rgb: bytes,
    art_w: int,
    art_h: int,
    *,
    scale: int,
    text_cols: int,
    mode: RenderMode,
    status: str,
    chat_rows: list[ChatRow],
    chat_lines: int,
) -> bytes:
    """Build one full RGB24 frame: video art, status bar, and chat overlay."""
    frame_w, frame_h = record_output_size(
        art_w,
        art_h,
        scale=scale,
        text_cols=text_cols,
        mode=mode,
        chat_lines=chat_lines,
    )
    frame = bytearray(frame_w * frame_h * 3)

    video_rgb, video_w, video_h = _upscale_art(art_rgb, art_w, art_h, scale, mode)
    _blit(frame, frame_w, frame_h, 0, 0, video_rgb, video_w, video_h)

    overlay_y = video_h
    overlay_h = frame_h - video_h
    _fill_rect(frame, frame_w, frame_h, 0, overlay_y, frame_w, overlay_h, OVERLAY_BG)

    _draw_text_line(
        frame,
        frame_w,
        frame_h,
        0,
        overlay_y,
        _ascii_safe(status[:text_cols]),
        STATUS_COLOR,
        scale,
        text_cols,
    )
    overlay_y += scale

    shown = chat_rows[-chat_lines:] if chat_lines > 0 else []
    pad = max(0, chat_lines - len(shown))
    for i in range(chat_lines):
        if i >= pad:
            _draw_chat_row(
                frame,
                frame_w,
                frame_h,
                0,
                overlay_y,
                shown[i - pad],
                scale,
                text_cols,
            )
        overlay_y += scale

    return bytes(frame)


def _video_output_size(art_w: int, art_h: int, scale: int, mode: RenderMode) -> tuple[int, int]:
    if mode == RenderMode.BLOCKS:
        return art_w * scale * 2, art_h * scale
    return art_w * scale, art_h * scale


def _upscale_art(
    rgb: bytes,
    art_w: int,
    art_h: int,
    scale: int,
    mode: RenderMode,
) -> tuple[bytes, int, int]:
    scaled = upscale_rgb(rgb, art_w, art_h, scale)
    if mode != RenderMode.BLOCKS:
        return scaled, art_w * scale, art_h * scale

    src_w = art_w * scale
    src_h = art_h * scale
    out_w = src_w * 2
    out = bytearray(out_w * src_h * 3)
    src_row_bytes = src_w * 3
    dst_row_bytes = out_w * 3
    for y in range(src_h):
        src_row = memoryview(scaled)[y * src_row_bytes : (y + 1) * src_row_bytes]
        dst = y * dst_row_bytes
        for x in range(src_w):
            pix = src_row[x * 3 : x * 3 + 3]
            di = dst + x * 6
            out[di : di + 3] = pix
            out[di + 3 : di + 6] = pix
    return bytes(out), out_w, src_h


def _glyph(code: int) -> bytes:
    idx = max(0, min(127, code)) * 8
    return _FONT_BYTES[idx : idx + 8]


def _ascii_safe(text: str) -> str:
    return "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in text)


def _set_pixel(buf: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if 0 <= x < width and 0 <= y < height:
        i = (y * width + x) * 3
        buf[i], buf[i + 1], buf[i + 2] = color


def _fill_rect(
    buf: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    w: int,
    h: int,
    color: tuple[int, int, int],
) -> None:
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(width, x + w)
    y1 = min(height, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    row_w = x1 - x0
    row = bytes(color) * row_w
    row_bytes = width * 3
    for row_y in range(y0, y1):
        start = row_y * row_bytes + x0 * 3
        buf[start : start + row_w * 3] = row


def _blit(
    dst: bytearray,
    dst_w: int,
    dst_h: int,
    x: int,
    y: int,
    src: bytes,
    src_w: int,
    src_h: int,
) -> None:
    if x == 0 and src_w == dst_w and y >= 0 and y + src_h <= dst_h:
        start = y * dst_w * 3
        dst[start : start + src_w * src_h * 3] = src
        return

    src_row_bytes = src_w * 3
    dst_row_bytes = dst_w * 3
    for row in range(src_h):
        dy = y + row
        if dy < 0 or dy >= dst_h:
            continue
        src_off = row * src_row_bytes
        dst_off = dy * dst_row_bytes
        if x >= 0 and x + src_w <= dst_w:
            dst[dst_off + x * 3 : dst_off + (x + src_w) * 3] = src[
                src_off : src_off + src_row_bytes
            ]
            continue
        for col in range(src_w):
            dx = x + col
            if dx < 0 or dx >= dst_w:
                continue
            si = src_off + col * 3
            di = dst_off + dx * 3
            dst[di : di + 3] = src[si : si + 3]


def _draw_char(
    buf: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    ch: str,
    color: tuple[int, int, int],
    cell: int,
) -> None:
    glyph = _glyph(ord(ch))
    scale = max(1, cell // 8)
    glyph_w = 8 * scale
    glyph_h = 8 * scale
    ox = x + max(0, (cell - glyph_w) // 2)
    oy = y + max(0, (cell - glyph_h) // 2)
    for row in range(8):
        bits = glyph[row]
        for col in range(8):
            # font8x8: LSB is the leftmost pixel in each row.
            if bits & (1 << col):
                for dy in range(scale):
                    for dx in range(scale):
                        _set_pixel(buf, width, height, ox + col * scale + dx, oy + row * scale + dy, color)


def _draw_text_line(
    buf: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    text: str,
    color: tuple[int, int, int],
    cell: int,
    max_cols: int,
) -> None:
    for i, ch in enumerate(text[:max_cols]):
        _draw_char(buf, width, height, x + i * cell, y, ch, color, cell)


def _draw_chat_row(
    buf: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    row: ChatRow,
    cell: int,
    max_cols: int,
) -> None:
    user = _ascii_safe(row.user)
    text = _ascii_safe(row.text)
    prefix = f"{user}: "
    avail = max(1, max_cols - len(prefix))
    if len(text) > avail:
        text = text[: max(1, avail - 1)] + "?"

    col = 0
    for ch in user:
        if col >= max_cols:
            return
        _draw_char(buf, width, height, x + col * cell, y, ch, row.user_color, cell)
        col += 1
    for ch in ": ":
        if col >= max_cols:
            return
        _draw_char(buf, width, height, x + col * cell, y, ch, TEXT_COLOR, cell)
        col += 1
    for ch in text:
        if col >= max_cols:
            return
        _draw_char(buf, width, height, x + col * cell, y, ch, TEXT_COLOR, cell)
        col += 1
