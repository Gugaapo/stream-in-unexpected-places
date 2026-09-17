"""Sink subpackage. Importing this package registers every built-in sink.

The medium of this repo is the **novel** (``novel`` / ``novel_txt``): a live stream narrated as
prose. ``ansi`` (terminal pixel art) ships as the core's reference sink and ``ppm_seq`` as the
debug/verification sink — both are one file each, no extra dependencies.
"""

from __future__ import annotations

from . import ansi, novel, ppm_seq  # noqa: F401  (import side effect: registration)

__all__ = ["ansi", "novel", "ppm_seq"]
