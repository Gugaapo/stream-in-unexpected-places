"""
streamkit — a library for playing a live stream into an unexpected medium.

    source  ->  Grid  ->  [FX chain]  ->  sink

A *source* produces frames (a Twitch stream via streamlink+ffmpeg, a local file, a direct URL, or a
deterministic synthetic pattern that needs no ffmpeg at all). A *Grid* is an RGB frame at a chosen
resolution. A *sink* is anything that can display, store or transmit that grid — a terminal, a piece
of prose, a spreadsheet, a wall of Minecraft maps.

This package is the shared library; the mediums built on it live in ``scripts/`` in the same
repository. To build a new one, see ``docs/writing-a-medium.md``.

    from streamkit.pipeline import run
    from streamkit.sink import build_sink, register
    from streamkit.sources import build_source

The library also ships a CLI that runs any source into the built-in sinks:

    streamkit --source twitch:oMeiaUm --size 160x48 --fps 12 --sink ansi
"""

from __future__ import annotations

from .grid import Grid
from .pipeline import RunResult, run
from .sink import Sink, build_sink, register, registered_sinks
from .sources import Source, build_source, chat_channel

# Importing the library registers the sinks that ship with it (ansi, ppm_seq).
from . import sinks as _sinks  # noqa: F401,E402  (registration side effect)

__all__ = [
    "Grid",
    "RunResult",
    "Sink",
    "Source",
    "build_sink",
    "build_source",
    "chat_channel",
    "register",
    "registered_sinks",
    "run",
    "__version__",
]

__version__ = "0.2.0"
