"""Locate ffmpeg without assuming it is on PATH.

Precedence: ``FFMPEG_PATH`` env var -> ``shutil.which("ffmpeg")`` -> a WinGet install dir.
This matters because the WSL side has no ffmpeg at all while the Windows host does, so the
code must be explicit about which one it found instead of failing with a bare FileNotFoundError.
"""

from __future__ import annotations

import os
import shutil
from glob import glob
from pathlib import Path

_WINGET_GLOBS = (
    "~/AppData/Local/Microsoft/WinGet/Packages/*FFmpeg*/**/bin/ffmpeg.exe",
    "~/.local/share/microsoft/winget/packages/*ffmpeg*/**/bin/ffmpeg",
)


class FfmpegNotFound(RuntimeError):
    pass


def find_ffmpeg() -> str:
    """Return a usable ffmpeg path, or raise FfmpegNotFound with actionable advice."""
    env = os.environ.get("FFMPEG_PATH")
    if env:
        if Path(env).is_file():
            return env
        raise FfmpegNotFound(f"FFMPEG_PATH is set to {env!r} but that file does not exist")

    found = shutil.which("ffmpeg")
    if found:
        return found

    for pattern in _WINGET_GLOBS:
        for hit in sorted(glob(os.path.expanduser(pattern), recursive=True)):
            if Path(hit).is_file():
                return hit

    raise FfmpegNotFound(
        "ffmpeg not found. Install it (Windows: winget install Gyan.FFmpeg; "
        "Debian/Ubuntu: sudo apt install ffmpeg) or point FFMPEG_PATH at the binary."
    )


def has_ffmpeg() -> bool:
    try:
        find_ffmpeg()
    except FfmpegNotFound:
        return False
    return True
