"""Vision-language describer seam for the novel sink.

Real calls go through OpenAI-compatible HTTP (stdlib urllib + SSE).
Tests inject ScriptedDescriber; NullDescriber lets the sink run with no key.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterator, Protocol

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash-vision-exp"

_ENV_LOADED = False
_KEY_NAMES = ("DEEPSEEK_API_KEY", "NOVEL_API_KEY")


def load_dotenv(path: str | os.PathLike[str] | None = None) -> Path | None:
    """Load ``KEY=VALUE`` pairs from a ``.env`` file into ``os.environ``.

    Existing environment variables win (``.env`` does not override the shell).
    Stdlib only — no python-dotenv dependency. Returns the path loaded, or None.
    """
    global _ENV_LOADED
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    else:
        cwd = Path.cwd()
        candidates.append(cwd / ".env")
        # Also try the package repo root (…/stream) when launched from elsewhere.
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "pyproject.toml").exists() or (parent / "setup.py").exists():
                candidates.append(parent / ".env")
                break

    loaded: Path | None = None
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
        loaded = candidate
        break
    _ENV_LOADED = True
    return loaded


def resolve_api_key(explicit: str | None = None) -> str | None:
    """``--novel-key`` wins, then env / ``.env``: DEEPSEEK_API_KEY / NOVEL_API_KEY."""
    if explicit:
        return explicit.strip() or None
    if not _ENV_LOADED:
        load_dotenv()
    for name in _KEY_NAMES:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return None


class DescribeError(Exception):
    """HTTP / transport failure from a real describer. Carries status + body."""

    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class Describer(Protocol):
    def describe(
        self,
        *,
        system: str,
        user: str,
        image_png: bytes,
        on_token: Callable[[str], None] | None = None,
    ) -> str: ...


class NullDescriber:
    """Always returns empty string — no network, no key."""

    def describe(
        self,
        *,
        system: str,
        user: str,
        image_png: bytes,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        return ""


class ScriptedDescriber:
    """Offline canned paragraphs; records every prompt for tests."""

    def __init__(
        self,
        paragraphs: list[str] | None = None,
        *,
        sleep: float = 0.0,
        loop: bool = True,
    ) -> None:
        self.paragraphs = list(paragraphs or ["The story continues in silence."])
        self.sleep = float(sleep)
        self.loop = bool(loop)
        self.calls: list[dict] = []
        self._i = 0

    def describe(
        self,
        *,
        system: str,
        user: str,
        image_png: bytes,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "image_png_len": len(image_png),
            }
        )
        if self.sleep > 0:
            time.sleep(self.sleep)
        if not self.paragraphs:
            text = ""
        elif self._i >= len(self.paragraphs):
            if not self.loop:
                text = ""
            else:
                text = self.paragraphs[self._i % len(self.paragraphs)]
                self._i += 1
        else:
            text = self.paragraphs[self._i]
            self._i += 1
        if on_token and text:
            # Deliver in small chunks so streaming UI paths get exercised.
            step = max(1, len(text) // 8)
            for i in range(0, len(text), step):
                on_token(text[i : i + step])
        return text


class OpenAICompatDescriber:
    """POST /chat/completions with image_url data URI; stream SSE deltas."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        timeout: float = 30.0,
        temperature: float = 1.1,
        max_tokens: int = 180,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
        self.model = model or DEFAULT_MODEL
        self.api_key = api_key
        self.timeout = float(timeout)
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)

    def describe(
        self,
        *,
        system: str,
        user: str,
        image_png: bytes,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        key = resolve_api_key(self.api_key)
        if not key:
            raise DescribeError("no API key (set DEEPSEEK_API_KEY or pass --novel-key)")
        last_err: DescribeError | None = None
        for attempt in range(2):
            try:
                return self._request(
                    system=system,
                    user=user,
                    image_png=image_png,
                    api_key=key,
                    on_token=on_token,
                )
            except DescribeError as exc:
                last_err = exc
                # 429: wait longer once, then give up this beat (retrying fast worsens limits).
                if attempt == 0 and exc.status == 429:
                    time.sleep(5.0)
                    continue
                retryable = (
                    exc.status is None
                    or exc.status == 408
                    or (exc.status is not None and exc.status >= 500)
                )
                if attempt == 0 and retryable:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise
        assert last_err is not None
        raise last_err

    def _endpoint(self) -> str:
        return self.base_url + "chat/completions"

    def _request(
        self,
        *,
        system: str,
        user: str,
        image_png: bytes,
        api_key: str,
        on_token: Callable[[str], None] | None,
    ) -> str:
        b64 = base64.b64encode(image_png).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "stream": True,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        # DeepSeek V4 defaults to thinking: with a small max_tokens budget the
        # entire reply lands in reasoning_content and visible content is "".
        if "deepseek" in self.base_url.lower() or "deepseek" in self.model.lower():
            payload["thinking"] = {"type": "disabled"}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint(),
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return "".join(self._iter_sse(resp, on_token))
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise DescribeError(
                f"HTTP {exc.code}: {err_body[:400]}",
                status=int(exc.code),
                body=err_body,
            ) from None
        except urllib.error.URLError as exc:
            raise DescribeError(f"URL error: {exc.reason}", status=None, body=str(exc)) from None
        except TimeoutError as exc:
            raise DescribeError(f"timeout: {exc}", status=408, body=str(exc)) from None

    def _iter_sse(self, resp, on_token: Callable[[str], None] | None) -> Iterator[str]:
        while True:
            raw = resp.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if not piece:
                # Some providers put the full message on the last chunk.
                msg = choices[0].get("message") or {}
                piece = msg.get("content")
            # Ignore reasoning_content — novel sink wants the final prose only.
            if piece:
                if on_token:
                    on_token(piece)
                yield piece
