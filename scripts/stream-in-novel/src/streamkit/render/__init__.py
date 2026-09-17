"""Renderer subpackage.

``terminal`` is a VERBATIM port of ``scripts/stream-in-terminal/src/stream_in_terminal/render.py``
(sha256-identical, 2026-09-16) — do not edit it, or the ANSI regression test loses its meaning.
"""

from __future__ import annotations

from .terminal import (
    BLOCKS_CHARS,
    DEFAULT_CHARS,
    RenderMode,
    frame_to_ascii,
    frame_to_blocks,
    frame_to_compact,
    pixel_dimensions,
    render_frame,
    resize_rgb,
    resolve_charset,
    resolve_render_mode,
    supports_truecolor,
)

__all__ = [
    "BLOCKS_CHARS",
    "DEFAULT_CHARS",
    "RenderMode",
    "frame_to_ascii",
    "frame_to_blocks",
    "frame_to_compact",
    "pixel_dimensions",
    "render_frame",
    "resize_rgb",
    "resolve_charset",
    "resolve_render_mode",
    "supports_truecolor",
]
