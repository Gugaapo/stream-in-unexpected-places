"""Pure story logic for the novel sink — no I/O, no network."""

from __future__ import annotations

from dataclasses import dataclass, field

from streamkit.grid import Grid

STYLES = ("dumb", "novel", "nature", "noir")
LANGS = ("pt-BR", "en", "auto")

_STYLE_SYSTEM = {
    "dumb": (
        "You are a snarky, slightly dumb friend watching the stream and narrating out loud. "
        "Roast the streamer with petty, affectionate mockery — wrong clicks, slow debugging, "
        "obvious mistakes, ego, dead air — while staying 100% precise about what is actually "
        "on screen and in chat. Never invent drama; the joke is the real scene. "
        "Third-person present or past is fine; keep it punchy and concrete."
    ),
    "novel": (
        "You are continuing a literary novel in third-person past tense — an ongoing chapter "
        "about what is happening on a live stream. Write vivid, specific prose."
    ),
    "nature": (
        "You are narrating a nature documentary that observes a human at a keyboard and the "
        "world on their screen. Calm, precise, slightly awed — as if David Attenborough watched Twitch."
    ),
    "noir": (
        "You are a hard-boiled detective narrating in second person. Rain, neon, bad decisions. "
        "Address the reader as 'you' and treat the stream as the case."
    ),
}

_LANG_RULE = {
    "pt-BR": "Write entirely in Brazilian Portuguese (pt-BR).",
    "en": "Write entirely in English.",
    "auto": (
        "Write in the dominant language of the chat lines below; "
        "if unclear, write in Brazilian Portuguese."
    ),
}

_COMMON_RULES = (
    "Continue the story; never restate what was already written. Write 2–4 sentences only. "
    "GROUNDING (anti-hallucination) — mandatory: "
    "Only describe what is visible in the still or stated in the chat block below. "
    "Never invent people, display names, chatters, dialogue, UI text, scores, errors, or events. "
    "Never invent a name (e.g. do not invent 'Falko'); if a person is unnamed on screen, say "
    "'the streamer' / 'someone on screen', not a made-up name. "
    "Never invent stream stats: viewer count, follower count, subscriber count, bits, uptime, "
    "live status badges, or 'X people watching'. If a number is not clearly legible in the still, "
    "omit it entirely — do not guess 500, 1000, or any other figure. "
    "Never invent how long the streamer has been debugging or streaming unless that duration "
    "is written on screen. "
    "Chat lines are tagged [STREAMER] or [CHAT]: "
    "[STREAMER] is the channel owner speaking in their own chat — treat them as the streamer, "
    "not as a random viewer. "
    "[CHAT] lines are other viewers — quote them by their exact username only. "
    "Only use usernames that appear in the chat block. "
    "Never mention images, cameras, screenshots, AI, models, timestamps, pixels, or other "
    "technical terms. Do not describe UI chrome as 'a menu' in meta terms — narrate the scene."
)


@dataclass
class StoryState:
    """Rolling paragraph buffer (keep at least the last 5)."""

    paragraphs: list[str] = field(default_factory=list)
    keep: int = 5

    def add(self, paragraph: str) -> None:
        text = (paragraph or "").strip()
        if not text:
            return
        self.paragraphs.append(text)
        if len(self.paragraphs) > max(self.keep, 5):
            self.paragraphs = self.paragraphs[-max(self.keep, 5) :]

    def tail(self, n: int = 3) -> list[str]:
        if n <= 0:
            return []
        return list(self.paragraphs[-n:])


def channel_slug(channel: str) -> str:
    """Normalise ``twitch:foo`` / ``FOO`` → ``foo`` for streamer matching."""
    raw = (channel or "").strip()
    if raw.lower().startswith("twitch:"):
        raw = raw.split(":", 1)[1]
    return raw.strip().lstrip("#").lower()


def is_streamer_user(user: str, channel: str) -> bool:
    """True when the chat username is the channel owner (case-insensitive)."""
    u = (user or "").strip().lstrip("#").lower()
    c = channel_slug(channel)
    return bool(u and c and u == c)


def build_prompt(
    state: StoryState,
    chat_lines: list[tuple[str, str]] | list[str],
    style: str,
    lang: str,
    channel: str,
) -> tuple[str, str]:
    """Return ``(system, user)`` prompt pair for the describer."""
    style_key = style if style in _STYLE_SYSTEM else "dumb"
    lang_key = lang if lang in _LANG_RULE else "pt-BR"
    channel_name = channel_slug(channel) or (channel or "the stream").strip() or "the stream"

    system = "\n".join(
        [
            _STYLE_SYSTEM[style_key],
            _LANG_RULE[lang_key],
            _COMMON_RULES,
            f"The channel / streamer login is '{channel_name}'.",
        ]
    )

    parts: list[str] = []
    tail = state.tail(3)
    if tail:
        parts.append("Previous paragraphs (continue from here; do not repeat):")
        for p in tail:
            parts.append(p)
    else:
        parts.append("This is the opening of the chapter. Begin the story from the scene.")

    normalised = _normalise_chat(chat_lines)
    if normalised:
        parts.append(
            "Recent chat (tagged; quote only these usernames; "
            f"[STREAMER] = channel owner '{channel_name}'):"
        )
        for user, text in normalised[-8:]:
            tag = "STREAMER" if is_streamer_user(user, channel_name) else "CHAT"
            parts.append(f"[{tag}] {user}: {text}")
    else:
        parts.append("No chat lines this beat.")

    parts.append("Continue. Stay grounded — invent nothing.")
    return system, "\n".join(parts)


def _normalise_chat(
    chat_lines: list[tuple[str, str]] | list[str],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in chat_lines or []:
        if isinstance(item, tuple) and len(item) >= 2:
            user, text = str(item[0]).strip(), str(item[1]).strip()
            if user or text:
                out.append((user or "anon", text))
        else:
            s = str(item).strip()
            if not s:
                continue
            if ":" in s:
                user, text = s.split(":", 1)
                out.append((user.strip() or "anon", text.strip()))
            else:
                out.append(("anon", s))
    return out


def should_describe(
    prev_grid: Grid | None,
    grid: Grid,
    chat_lines: list,
    last_chat_count: int,
    threshold: float,
) -> bool:
    """Change gate: skip near-identical frames unless chat produced new lines."""
    chat_n = len(chat_lines or [])
    if chat_n > last_chat_count:
        return True
    if prev_grid is None:
        return True
    try:
        mae = grid.mean_abs_error(prev_grid)
    except ValueError:
        return True
    return mae >= float(threshold)
