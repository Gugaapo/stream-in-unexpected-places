"""Encode terminal pixel-art frames to an MP4 file via ffmpeg."""

from __future__ import annotations

import re
import subprocess
import threading
from datetime import datetime


def default_record_path(channel: str) -> str:
    """Build a safe default output filename for a channel recording."""
    safe = re.sub(r"[^\w\-]+", "_", channel.lower()).strip("_") or "stream"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe}_{ts}.mp4"


def upscale_rgb(rgb: bytes, src_w: int, src_h: int, scale: int) -> bytes:
    """Nearest-neighbor upscale of an RGB24 buffer (row-wise, fast)."""
    if scale < 1:
        raise ValueError("scale must be >= 1")
    if scale == 1:
        return rgb
    dst_w = src_w * scale
    dst_h = src_h * scale
    expected = src_w * src_h * 3
    if len(rgb) < expected:
        raise ValueError("rgb buffer shorter than src dimensions")

    out = bytearray(dst_w * dst_h * 3)
    scaled_row = bytearray(dst_w * 3)
    dst_row_bytes = dst_w * 3

    for sy in range(src_h):
        src_row = memoryview(rgb)[sy * src_w * 3 : (sy + 1) * src_w * 3]
        di = 0
        for sx in range(src_w):
            pix = src_row[sx * 3 : sx * 3 + 3]
            for _ in range(scale):
                scaled_row[di : di + 3] = pix
                di += 3
        base = sy * scale * dst_row_bytes
        for dy in range(scale):
            start = base + dy * dst_row_bytes
            out[start : start + dst_row_bytes] = scaled_row
    return bytes(out)


class Mp4Recorder:
    """Pipe composed RGB24 frames into ffmpeg for H.264 MP4 output."""

    def __init__(
        self,
        path: str,
        *,
        frame_width: int,
        frame_height: int,
        fps: float,
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        if frame_width < 1 or frame_height < 1:
            raise ValueError("frame dimensions must be >= 1")

        self.path = path
        self.out_w = frame_width
        self.out_h = frame_height
        self.fps = fps
        self._frame_bytes = self.out_w * self.out_h * 3
        self._frames_written = 0
        self._closed = False
        self._stderr = b""

        cmd = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{self.out_w}x{self.out_h}",
            "-r",
            f"{fps:.3f}",
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-movflags",
            "+faststart",
            "-y",
            path,
        ]
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Drain stderr so a full pipe cannot deadlock the encoder.
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            name="mp4-recorder-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    @property
    def frames_written(self) -> int:
        return self._frames_written

    def write_frame(self, rgb: bytes) -> None:
        if self._closed:
            raise RuntimeError("recorder is closed")
        if len(rgb) != self._frame_bytes:
            raise ValueError(
                f"expected {self._frame_bytes} frame bytes, got {len(rgb)}"
            )
        assert self._process.stdin is not None

        try:
            self._process.stdin.write(rgb)
        except BrokenPipeError as exc:
            self._raise_ffmpeg_error(exc)
        self._frames_written += 1

    def _drain_stderr(self) -> None:
        if not self._process.stderr:
            return
        chunks: list[bytes] = []
        try:
            while True:
                chunk = self._process.stderr.read(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError:
            pass
        self._stderr = b"".join(chunks)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._process.stdin:
            try:
                self._process.stdin.close()
            except OSError:
                pass

        try:
            rc = self._process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
            raise RuntimeError("ffmpeg encoder timed out while finalizing recording")

        if self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=2.0)
        stderr = self._stderr

        if rc != 0:
            msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(msg or f"ffmpeg exited with code {rc}")

    def __enter__(self) -> Mp4Recorder:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _raise_ffmpeg_error(self, cause: Exception) -> None:
        if self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1.0)
        msg = self._stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(msg or "ffmpeg encoder stopped unexpectedly") from cause
