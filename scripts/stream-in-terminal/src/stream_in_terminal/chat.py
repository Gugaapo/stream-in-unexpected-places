"""Read Twitch chat via anonymous IRC (justinfan) — no OAuth required."""

from __future__ import annotations

import random
import re
import socket
import ssl
import threading
from collections import deque
from dataclasses import dataclass

IRC_HOST = "irc.chat.twitch.tv"
IRC_PORT = 6697

_PRIVMSG_RE = re.compile(
    r"^(?:@(?P<tags>[^\s]+)\s+)?"
    r":(?:(?P<nick>[^!]+)![^\s]+\s+)?"
    r"PRIVMSG\s+#\S+\s+:(?P<msg>.*)$"
)


@dataclass(frozen=True)
class ChatMessage:
    user: str
    text: str
    color_hex: str | None = None  # Twitch tag e.g. #FF0000, if set


@dataclass(frozen=True)
class ChatRow:
    """One chat line prepared for terminal or video overlay rendering."""

    user: str
    text: str
    user_color: tuple[int, int, int]


# Distinct fallback hues when Twitch sends no user color.
_FALLBACK_RGB: tuple[tuple[int, int, int], ...] = (
    (255, 99, 71),    # tomato
    (255, 165, 0),    # orange
    (255, 215, 0),    # gold
    (50, 205, 50),    # limegreen
    (0, 206, 209),    # darkturquoise
    (30, 144, 255),   # dodgerblue
    (138, 43, 226),   # blueviolet
    (255, 105, 180),  # hotpink
    (0, 250, 154),    # mediumspringgreen
    (255, 140, 0),    # darkorange
    (64, 224, 208),   # turquoise
    (186, 85, 211),   # mediumorchid
    (127, 255, 0),    # chartreuse
    (70, 130, 180),   # steelblue
    (240, 128, 128),  # lightcoral
    (0, 191, 255),    # deepskyblue
)


def _parse_hex_color(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) != 6:
        return None
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return None


def user_rgb(user: str, color_hex: str | None = None) -> tuple[int, int, int]:
    """Stable RGB for a chat user: Twitch color if present, else hash palette."""
    parsed = _parse_hex_color(color_hex)
    if parsed is not None:
        # Avoid near-black on dark terminals
        if sum(parsed) < 80:
            return _FALLBACK_RGB[hash(user.lower()) % len(_FALLBACK_RGB)]
        return parsed
    return _FALLBACK_RGB[hash(user.lower()) % len(_FALLBACK_RGB)]


class TwitchChat:
    """Background IRC client that keeps the latest N chat messages."""

    def __init__(self, channel: str, max_messages: int = 5) -> None:
        self.channel = channel.lower().lstrip("#")
        self.max_messages = max(1, max_messages)
        self._messages: deque[ChatMessage] = deque(maxlen=self.max_messages)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = "connecting…"
        self._connected = False

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    def latest(self) -> list[ChatMessage]:
        with self._lock:
            return list(self._messages)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="twitch-chat",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def __enter__(self) -> TwitchChat:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()

    def _set_status(self, text: str) -> None:
        with self._lock:
            self._status = text

    def _push(self, user: str, text: str, color_hex: str | None = None) -> None:
        text = text.replace("\r", "").replace("\n", " ").strip()
        if not text:
            return
        with self._lock:
            self._messages.append(
                ChatMessage(user=user, text=text, color_hex=color_hex or None)
            )

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._session()
                backoff = 1.0
            except OSError as exc:
                self._connected = False
                self._set_status(f"chat reconnecting ({exc})")
                if self._stop.wait(backoff):
                    break
                backoff = min(30.0, backoff * 2)
            except Exception as exc:  # noqa: BLE001 — keep chat thread alive
                self._connected = False
                self._set_status(f"chat error: {exc}")
                if self._stop.wait(backoff):
                    break
                backoff = min(30.0, backoff * 2)

    def _session(self) -> None:
        nick = f"justinfan{random.randint(10000, 99999)}"
        raw = socket.create_connection((IRC_HOST, IRC_PORT), timeout=15)
        context = ssl.create_default_context()
        sock = context.wrap_socket(raw, server_hostname=IRC_HOST)
        sock.settimeout(1.0)
        self._set_status("chat joining…")

        def send(line: str) -> None:
            sock.sendall((line + "\r\n").encode("utf-8"))

        try:
            send("CAP REQ :twitch.tv/tags twitch.tv/commands")
            send("PASS SCHMOOPIIE")
            send(f"NICK {nick}")
            send(f"JOIN #{self.channel}")

            buf = ""
            while not self._stop.is_set():
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    raise OSError("IRC connection closed")
                buf += chunk.decode("utf-8", errors="replace")
                while "\r\n" in buf:
                    line, buf = buf.split("\r\n", 1)
                    self._handle_line(line, send)
        finally:
            self._connected = False
            try:
                sock.close()
            except OSError:
                pass

    def _handle_line(self, line: str, send) -> None:
        if not line:
            return
        if line.startswith("PING "):
            send("PONG " + line[5:])
            return

        # Welcome / join confirmation
        if " 001 " in line or " JOIN #" in line.upper() or line.startswith(":tmi.twitch.tv"):
            if " 001 " in line or f"#{self.channel}" in line.lower():
                self._connected = True
                self._set_status("chat live")

        m = _PRIVMSG_RE.match(line)
        if not m:
            return
        tags = m.group("tags") or ""
        nick = m.group("nick") or "unknown"
        msg = m.group("msg") or ""
        display = nick
        color_hex: str | None = None
        for part in tags.split(";"):
            if part.startswith("display-name=") and part[13:]:
                display = part[13:]
            elif part.startswith("color=") and part[6:]:
                color_hex = part[6:]
        self._push(display, msg, color_hex)
        if not self._connected:
            self._connected = True
            self._set_status("chat live")


def prepare_chat_rows(
    messages: list[ChatMessage],
    width: int,
    lines: int = 5,
    *,
    color: bool = True,
) -> list[ChatRow]:
    """Build structured chat rows for recording overlays."""
    width = max(8, width)
    shown = messages[-lines:]
    rows: list[ChatRow] = []
    for msg in shown:
        user = msg.user.replace("\n", " ")
        text = msg.text.replace("\r", "").replace("\n", " ").strip()
        if not text:
            continue
        prefix_plain = f"{user}: "
        avail = max(1, width - len(prefix_plain))
        if len(text) > avail:
            text = text[: max(1, avail - 1)] + "…"
        user_color = user_rgb(user, msg.color_hex) if color else (180, 180, 180)
        rows.append(ChatRow(user=user, text=text, user_color=user_color))
    return rows


def format_chat_block(
    messages: list[ChatMessage],
    width: int,
    lines: int = 5,
    color: bool = True,
    placeholder: str = "",
) -> str:
    """Render exactly `lines` chat rows, newest at the bottom, padded above."""
    width = max(8, width)
    shown = messages[-lines:]
    pad = lines - len(shown)
    rows: list[str] = []
    for _ in range(pad):
        rows.append(_fit(placeholder, width))
    for msg in shown:
        rows.append(_format_message(msg, width, color))
    return "\n".join(rows)


def _format_message(msg: ChatMessage, width: int, color: bool) -> str:
    user = msg.user.replace("\n", " ")
    text = msg.text
    prefix_plain = f"{user}: "
    avail = max(1, width - len(prefix_plain))
    if len(text) > avail:
        text = text[: max(1, avail - 1)] + "…"
    if color:
        r, g, b = user_rgb(user, msg.color_hex)
        colored = f"\x1b[38;2;{r};{g};{b}m{user}\x1b[0m: {text}"
        return _fit_ansi(colored, width, plain_len=len(prefix_plain) + len(text))
    return _fit(prefix_plain + text, width)


def _fit(text: str, width: int) -> str:
    if len(text) <= width:
        return text + (" " * (width - len(text)))
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _fit_ansi(text: str, width: int, plain_len: int) -> str:
    if plain_len <= width:
        return text + (" " * (width - plain_len))
    return text  # already truncated in plain form before ANSI wrap
