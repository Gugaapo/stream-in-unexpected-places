"""Spawn ffmpeg to decode a stream into raw RGB24 frames."""

from __future__ import annotations

import queue
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class FrameSource:
    """Readable RGB24 frame stream from ffmpeg."""

    process: subprocess.Popen[bytes]
    width: int
    height: int

    @property
    def frame_bytes(self) -> int:
        return self.width * self.height * 3

    def frames(self) -> Iterator[bytes]:
        assert self.process.stdout is not None
        size = self.frame_bytes
        while True:
            buf = self.process.stdout.read(size)
            if not buf or len(buf) < size:
                break
            yield buf

    def frames_interruptible(self, poll_s: float = 0.25) -> Iterator[bytes]:
        """
        Yield frames via a reader thread so waiting can be interrupted (Ctrl+C).

        Blocking pipe reads on Windows often swallow KeyboardInterrupt; polling
        a queue lets the main thread stay responsive.
        """
        q: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
        stop = threading.Event()

        def _reader() -> None:
            try:
                for frame in self.frames():
                    if stop.is_set():
                        break
                    while not stop.is_set():
                        try:
                            q.put(frame, timeout=0.25)
                            break
                        except queue.Full:
                            # Drop oldest buffered frame to stay live.
                            try:
                                q.get_nowait()
                            except queue.Empty:
                                pass
            finally:
                try:
                    q.put_nowait(None)
                except queue.Full:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        q.put_nowait(None)
                    except queue.Full:
                        pass

        thread = threading.Thread(target=_reader, name="ffmpeg-frames", daemon=True)
        thread.start()
        try:
            while True:
                try:
                    item = q.get(timeout=poll_s)
                except queue.Empty:
                    if self.process.poll() is not None and not thread.is_alive():
                        break
                    continue
                if item is None:
                    break
                yield item
        finally:
            stop.set()

    def close(self) -> None:
        if self.process.stdout:
            try:
                self.process.stdout.close()
            except OSError:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def __enter__(self) -> FrameSource:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def open_rgb_pipe(
    stream_url: str,
    width: int,
    height: int,
    fps: float,
    ffmpeg_path: str = "ffmpeg",
) -> FrameSource:
    """
    Start ffmpeg reading stream_url and writing raw rgb24 frames to stdout.

    width/height are the decode grid (later resampled to the terminal).
    """
    if width < 1 or height < 1:
        raise ValueError("width and height must be >= 1")

    # Twitch HLS often needs a browser-like UA; streamlink URLs may already embed tokens.
    headers = "User-Agent: Mozilla/5.0\r\n"

    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-headers",
        headers,
        "-i",
        stream_url,
        "-an",
        "-vf",
        f"fps={fps},scale={width}:{height}:flags=fast_bilinear",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=width * height * 3 * 2,
    )
    return FrameSource(process=proc, width=width, height=height)
