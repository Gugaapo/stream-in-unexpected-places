"""Novel sinks. Importing this package registers ``novel`` (ANSI) and ``novel_txt`` (plain text)."""

from __future__ import annotations

from . import novel  # noqa: F401  (import side effect: registration)

__all__ = ["novel"]
