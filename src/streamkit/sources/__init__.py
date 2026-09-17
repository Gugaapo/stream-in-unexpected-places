"""Sources: everything that can produce Grid frames.

Spec strings accepted by :func:`build_source`:

    pattern:bars | pattern:square | pattern:sweep | pattern:noise   (no ffmpeg, deterministic)
    file:/path/to/video.mp4                                        (ffmpeg, local file)
    url:https://...m3u8                                            (ffmpeg, direct media URL)
    twitch:<channel> | <channel> | https://twitch.tv/<channel>     (streamlink/yt-dlp + ffmpeg)
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

from ..grid import Grid
from .pattern import PATTERN_NAMES, PatternSource

# Concrete sources are exported so a medium can drive one directly (its own player loop) instead of
# going through the ``build_source`` spec string.
from .live import FileSource, TwitchSource, UrlSource  # noqa: E402

__all__ = [
    "FileSource",
    "PATTERN_NAMES",
    "PatternSource",
    "Source",
    "TwitchSource",
    "UrlSource",
    "build_source",
    "chat_channel",
]


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


def chat_channel(source: Source) -> str | None:
    """The Twitch channel a source reads from, if it is a Twitch source.

    ``None`` for ``pattern:`` / ``file:`` / ``url:`` sources. Mediums that display or narrate chat
    use this instead of parsing the source spec themselves.
    """
    channel = getattr(source, "channel", None)
    if isinstance(channel, str) and channel.strip():
        return channel.strip().lower()
    return None
