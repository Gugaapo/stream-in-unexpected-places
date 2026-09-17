"""Backward-compatible re-exports; prefer stream_in_terminal.render."""

from stream_in_terminal.render import (
    BLOCKS_CHARS,
    DEFAULT_CHARS,
    frame_to_ascii,
    resize_rgb,
    resolve_charset,
    supports_truecolor,
)

__all__ = [
    "BLOCKS_CHARS",
    "DEFAULT_CHARS",
    "frame_to_ascii",
    "resize_rgb",
    "resolve_charset",
    "supports_truecolor",
]
