"""
streamkit — play a live stream into an unexpected medium.

    source  ->  Grid  ->  [FX chain]  ->  sink

A *source* produces frames (a Twitch stream via streamlink+ffmpeg, a local file, or a
deterministic synthetic pattern that needs no ffmpeg at all). A *Grid* is an RGB frame at a
chosen resolution. A *sink* is anything that can display, store or transmit that grid.

This repo ships one medium: **novel** — a vision model reads the stream and writes it as prose
into your terminal, with Twitch chat as dialogue. ``ansi`` and ``ppm_seq`` are the reference and
debug sinks inherited from the shared core.
"""

from __future__ import annotations

from .grid import Grid
from .sink import Sink, build_sink, register, registered_sinks
from .sources import build_source

__all__ = [
    "Grid",
    "Sink",
    "build_sink",
    "build_source",
    "register",
    "registered_sinks",
    "__version__",
]

__version__ = "0.1.0"
