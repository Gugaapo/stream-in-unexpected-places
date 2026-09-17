"""Sink subpackage. Importing it registers the sinks that ship with the library.

``ansi`` (terminal pixel art) and ``ppm_seq`` (one PPM per frame) are the reference sinks: they show
what a sink looks like and give every medium a way to eyeball its frames without extra dependencies.
Medium projects live outside the library and register their own sinks with
:func:`streamkit.sink.register`.
"""

from __future__ import annotations

from . import ansi, ppm_seq  # noqa: F401  (import side effect: registration)

__all__ = ["ansi", "ppm_seq"]
