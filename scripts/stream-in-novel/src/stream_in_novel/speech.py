"""oMeiaUm live speech from the public transcription API.

Docs: https://meiaum.vinnytasso.com.br/developers/transcription
Read-only, no key. ``GET /api/v1/live/transcripts`` returns the latest lines
of the current broadcast. This replaces guessing dialogue from the picture.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

LIVE_URL = "https://meiaum.vinnytasso.com.br/api/v1/live/transcripts"
OMEIAUM_CHANNELS = frozenset({"omeiaum", "meiaum"})


@dataclass(frozen=True)
class SpeechLine:
    id: int
    speaker: str
    text: str


def speech_enabled(mode: str, channel: str | None) -> bool:
    """``auto`` turns the client on only for the oMeiaUm channel."""
    choice = (mode or "auto").strip().lower()
    if choice in ("off", "none", "0", "false"):
        return False
    if choice in ("on", "meiaum", "omeiaum"):
        return True
    slug = (channel or "").strip().lstrip("#").lower()
    if slug.startswith("twitch:"):
        slug = slug.split(":", 1)[1]
    return slug in OMEIAUM_CHANNELS


def parse_live_transcripts(payload: dict, *, limit: int = 8) -> list[SpeechLine]:
    """Newest ``limit`` final lines, oldest first."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    lines: list[SpeechLine] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if item.get("is_final") is False:
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        speaker_obj = item.get("speaker") or {}
        if isinstance(speaker_obj, dict):
            speaker = str(speaker_obj.get("name") or speaker_obj.get("id") or "unknown")
        else:
            speaker = str(speaker_obj or "unknown")
        try:
            line_id = int(item.get("id") or 0)
        except (TypeError, ValueError):
            line_id = 0
        lines.append(SpeechLine(id=line_id, speaker=speaker, text=text))
    lines.sort(key=lambda line: line.id)
    if limit > 0:
        lines = lines[-limit:]
    return lines


class MeiaUmSpeech:
    """Poll the public live-transcript endpoint. Failures stay local."""

    def __init__(self, *, timeout: float = 8.0, url: str = LIVE_URL) -> None:
        self.timeout = float(timeout)
        self.url = url
        self.status = "speech connecting…"

    def latest(self, limit: int = 8) -> list[SpeechLine]:
        query = f"{self.url}?limit={int(limit)}"
        req = urllib.request.Request(
            query,
            method="GET",
            headers={
                "Accept": "application/json",
                # The API answers 403 to urllib's default agent.
                "User-Agent": "stream-in-novel",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.status = f"speech HTTP {exc.code}"
            return []
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            self.status = f"speech down ({type(exc).__name__})"
            return []
        lines = parse_live_transcripts(payload, limit=limit)
        self.status = f"speech {len(lines)}" if lines else "speech idle"
        return lines
