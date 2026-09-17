"""Resolve Twitch channel/URL to a playable HLS stream URL."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

TWITCH_HOSTS = {"twitch.tv", "www.twitch.tv", "m.twitch.tv"}

# Map friendly quality labels to streamlink stream names / yt-dlp format hints.
QUALITY_MAP = {
    "best": "best",
    "worst": "worst",
    "1080p": "1080p60,1080p,best",
    "720p": "720p60,720p,best",
    "480p": "480p,worst",
    "360p": "360p,worst",
    "160p": "160p,worst",
}


class StreamResolveError(Exception):
    """Raised when a live stream URL cannot be resolved."""


def parse_channel(value: str) -> str:
    """Extract a Twitch channel login from a bare name or URL."""
    value = value.strip()
    if not value:
        raise StreamResolveError("Channel name or URL is required.")

    if "://" in value or value.startswith("twitch.tv/") or value.startswith("www.twitch.tv/"):
        if "://" not in value:
            value = "https://" + value
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if host and "twitch.tv" not in host:
            raise StreamResolveError(f"Not a Twitch URL: {value}")
        path = parsed.path.strip("/")
        if not path:
            raise StreamResolveError(f"No channel in URL: {value}")
        channel = path.split("/")[0]
    else:
        channel = value.lstrip("@")

    channel = channel.lower()
    if not re.fullmatch(r"[a-z0-9_]{1,25}", channel):
        raise StreamResolveError(f"Invalid Twitch channel name: {channel!r}")
    return channel


def _run_capture(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _sibling_exe(name: str) -> str | None:
    """Find a console tool next to the current Python (venv Scripts / bin)."""
    folder = Path(sys.executable).resolve().parent
    candidates = [folder / name]
    if sys.platform == "win32":
        candidates.extend([folder / f"{name}.exe", folder / f"{name}.cmd"])
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _find_tool(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name) or _sibling_exe(name)
        if found:
            return found
    return None


def _streamlink_cmd() -> list[str] | None:
    exe = _find_tool("streamlink")
    if exe:
        return [exe]
    # Module entry when installed but Scripts not on PATH
    code, _, _ = _run_capture(
        [sys.executable, "-c", "import streamlink.main"]
    )
    if code == 0:
        return [sys.executable, "-m", "streamlink"]
    return None


def _ytdlp_cmd() -> list[str] | None:
    exe = _find_tool("yt-dlp", "yt_dlp")
    if exe:
        return [exe]
    code, _, _ = _run_capture(
        [sys.executable, "-c", "import yt_dlp"]
    )
    if code == 0:
        return [sys.executable, "-m", "yt_dlp"]
    return None


def _resolve_streamlink(channel: str, quality: str) -> str:
    base = _streamlink_cmd()
    if not base:
        raise FileNotFoundError("streamlink")

    stream_spec = QUALITY_MAP.get(quality.lower(), quality)
    names = [s.strip() for s in stream_spec.split(",") if s.strip()]
    url = f"https://www.twitch.tv/{channel}"

    last_err = ""
    for name in names:
        code, out, err = _run_capture([*base, "--stream-url", url, name])
        if code == 0 and out.startswith("http"):
            return out.splitlines()[0].strip()
        last_err = err or out or f"exit {code}"

    raise StreamResolveError(
        f"Stream offline or not found for '{channel}' via streamlink. {last_err}"
    )


def _resolve_ytdlp(channel: str, quality: str) -> str:
    base = _ytdlp_cmd()
    if not base:
        raise FileNotFoundError("yt-dlp")

    url = f"https://www.twitch.tv/{channel}"
    fmt = "best"
    m = re.match(r"(\d+)p", quality.lower())
    if quality.lower() == "worst":
        fmt = "worst"
    elif m:
        h = m.group(1)
        fmt = f"best[height<={h}]/best"

    code, out, err = _run_capture(
        [*base, "-g", "-f", fmt, "--no-playlist", url]
    )
    if code == 0 and out.startswith("http"):
        return out.splitlines()[0].strip()

    raise StreamResolveError(
        f"Stream offline or not found for '{channel}' via yt-dlp. {err or out or f'exit {code}'}"
    )


def resolve_stream_url(channel_or_url: str, quality: str = "best") -> tuple[str, str]:
    """
    Resolve a Twitch channel/URL to an HLS (or similar) media URL.

    Returns (channel, stream_url).
    Tries streamlink first, then yt-dlp.
    """
    channel = parse_channel(channel_or_url)
    resolver_errors: list[str] = []
    missing: list[str] = []

    if _streamlink_cmd():
        try:
            return channel, _resolve_streamlink(channel, quality)
        except StreamResolveError as exc:
            resolver_errors.append(str(exc))
        except FileNotFoundError:
            missing.append("streamlink")
    else:
        missing.append("streamlink")

    if _ytdlp_cmd():
        try:
            return channel, _resolve_ytdlp(channel, quality)
        except StreamResolveError as exc:
            resolver_errors.append(str(exc))
        except FileNotFoundError:
            missing.append("yt-dlp")
    else:
        missing.append("yt-dlp")

    if resolver_errors:
        # Tools ran but could not get a playable stream (usually offline).
        raise StreamResolveError(resolver_errors[0])

    raise StreamResolveError(
        "Could not resolve stream. Install streamlink (preferred) or yt-dlp, "
        f"and ensure the channel is live. Missing: {', '.join(missing) or 'resolvers'}."
    )


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg") or _sibling_exe("ffmpeg")
    if not path:
        raise StreamResolveError(
            "ffmpeg not found on PATH. Install ffmpeg and try again."
        )
    return path
