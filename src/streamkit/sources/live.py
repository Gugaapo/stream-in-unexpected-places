"""Live sources: a real Twitch stream, or a local video file, decoded through ffmpeg.

Both wrap the verbatim-port ``ffmpeg_source`` module (the proven live-in-terminal pipe reader,
which already handles Windows stdin/stdout buffering and interruptible reads).
"""

from __future__ import annotations

from collections.abc import Iterator

from ..ffmpeg import find_ffmpeg
from ..grid import Grid
from . import ffmpeg_source, twitch


class _PipeSource:
    """Shared plumbing: open an ffmpeg RGB pipe, yield Grids, always close the process."""

    def __init__(
        self,
        *,
        width: int,
        height: int,
        fps: float,
        ffmpeg_path: str | None = None,
    ) -> None:
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self._ffmpeg = ffmpeg_path
        self._source: ffmpeg_source.FrameSource | None = None
        self._closed = False
        self.frames_yielded = 0

    def _open(self, url: str) -> ffmpeg_source.FrameSource:
        ffmpeg = self._ffmpeg or find_ffmpeg()
        self._source = ffmpeg_source.open_rgb_pipe(
            url, self.width, self.height, self.fps, ffmpeg_path=ffmpeg
        )
        return self._source

    def frames(self) -> Iterator[Grid]:
        if self._source is None:
            raise RuntimeError("source is not opened (call open() first)")
        for raw in self._source.frames_interruptible():
            if self._closed:
                break
            grid = Grid.from_raw(
                raw,
                self.width,
                self.height,
                index=self.frames_yielded,
                t=self.frames_yielded / self.fps,
                meta={"source": self.name, "fps": self.fps},
            )
            self.frames_yielded += 1
            yield grid

    def stderr(self) -> bytes:
        """ffmpeg's stderr so far — call after frames() ends to explain a failure."""
        if self._source is None or self._source.process.stderr is None:
            return b""
        try:
            return self._source.process.stderr.read() or b""
        except OSError:
            return b""

    def close(self) -> None:
        self._closed = True
        if self._source is not None:
            self._source.close()
            self._source = None


class TwitchSource(_PipeSource):
    """A live Twitch channel (public streams need no API key)."""

    def __init__(
        self,
        channel: str,
        *,
        width: int = 160,
        height: int = 48,
        fps: float = 12.0,
        quality: str = "best",
        ffmpeg_path: str | None = None,
    ) -> None:
        super().__init__(width=width, height=height, fps=fps, ffmpeg_path=ffmpeg_path)
        self.requested = channel
        self.quality = quality
        self.channel = twitch.parse_channel(channel) if _looks_like_twitch(channel) else channel
        self.name = f"twitch:{self.channel}"
        self.resolved_url: str | None = None

    def open(self) -> None:
        """Resolve the channel to an HLS URL and start ffmpeg. Raises StreamResolveError."""
        resolved_channel, url = twitch.resolve_stream_url(self.requested, self.quality)
        self.channel = resolved_channel
        self.name = f"twitch:{resolved_channel}"
        self.resolved_url = url
        self._open(url)

    def __enter__(self) -> TwitchSource:
        self.open()
        return self


class FileSource(_PipeSource):
    """A local video file — the offline stand-in for a live stream."""

    def __init__(
        self,
        path: str,
        *,
        width: int = 160,
        height: int = 48,
        fps: float = 12.0,
        ffmpeg_path: str | None = None,
    ) -> None:
        super().__init__(width=width, height=height, fps=fps, ffmpeg_path=ffmpeg_path)
        self.path = path
        self.name = f"file:{path}"

    def open(self) -> None:
        self._open(self.path)

    def __enter__(self) -> FileSource:
        self.open()
        return self


class UrlSource(_PipeSource):
    """A direct media URL (HLS/DASH/progressive) — e.g. an already-resolved Twitch playlist."""

    def __init__(
        self,
        url: str,
        *,
        width: int = 160,
        height: int = 48,
        fps: float = 12.0,
        ffmpeg_path: str | None = None,
    ) -> None:
        super().__init__(width=width, height=height, fps=fps, ffmpeg_path=ffmpeg_path)
        self.url = url
        self.name = f"url:{url.split('?', 1)[0]}"

    def open(self) -> None:
        self._open(self.url)

    def __enter__(self) -> UrlSource:
        self.open()
        return self


def _looks_like_twitch(value: str) -> bool:
    lowered = value.lower()
    return "twitch.tv" in lowered or "/" not in value
