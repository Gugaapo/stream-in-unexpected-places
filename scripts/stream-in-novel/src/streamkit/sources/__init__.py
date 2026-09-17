"""Sources: everything that can produce Grid frames.

Spec strings accepted by :func:`build_source`:

    pattern:bars | pattern:square | pattern:sweep | pattern:noise   (no ffmpeg, deterministic)
    file:/path/to/video.mp4                                        (ffmpeg, local file)
    twitch:<channel> | <channel> | https://twitch.tv/<channel>     (streamlink/yt-dlp + ffmpeg)
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

from ..grid import Grid
from .pattern import PATTERN_NAMES, PatternSource

__all__ = ["PATTERN_NAMES", "PatternSource", "Source", "build_source"]


@runtime_checkable
class Source(Protocol):
    name: str
    width: int
    height: int
    fps: float

    def frames(self) -> Iterator[Grid]: ...

    def close(self) -> None: ...


def build_source(
    spec: str,
    *,
    width: int = 160,
    height: int = 48,
    fps: float = 12.0,
    quality: str = "best",
    seed: int = 1234,
    ffmpeg_path: str | None = None,
) -> Source:
    """Build a source from a spec string (see the module docstring)."""
    if width < 1 or height < 1:
        raise ValueError("width and height must be >= 1")

    text = (spec or "").strip()
    if not text:
        raise ValueError("empty source spec")

    if text.startswith("pattern:"):
        name = text.split(":", 1)[1]
        return PatternSource(name, width=width, height=height, fps=fps, seed=seed)

    if text.startswith("file:"):
        from .live import FileSource

        return FileSource(text.split(":", 1)[1], width=width, height=height, fps=fps,
                          ffmpeg_path=ffmpeg_path)

    if text.startswith("twitch:"):
        text = text.split(":", 1)[1]

    # A bare http(s) URL is a direct media/HLS URL, not a channel — but twitch.tv links are
    # channels, so those must still go through the resolver.
    if text.startswith("url:"):
        from .live import UrlSource

        return UrlSource(text.split(":", 1)[1], width=width, height=height, fps=fps,
                         ffmpeg_path=ffmpeg_path)
    if "twitch.tv" not in text.lower() and text.lower().startswith(("http://", "https://")):
        from .live import UrlSource

        return UrlSource(text, width=width, height=height, fps=fps, ffmpeg_path=ffmpeg_path)

    from .live import TwitchSource

    return TwitchSource(text, width=width, height=height, fps=fps, quality=quality,
                        ffmpeg_path=ffmpeg_path)
