"""The describer seam reports transport failures as DescribeError, never as a bare traceback.

These tests must not depend on the ambient environment (a developer machine really does have
DEEPSEEK_API_KEY exported), so key resolution is exercised with a patched environment.
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamkit.describe as describe  # noqa: E402
from streamkit.describe import (  # noqa: E402
    DescribeError,
    NullDescriber,
    OpenAICompatDescriber,
    ScriptedDescriber,
)

KEY_NAMES = ("DEEPSEEK_API_KEY", "NOVEL_API_KEY")


def _no_keys():
    """An environment with no key, and no .env loading (patching the module's latch)."""
    env = {k: v for k, v in os.environ.items() if k not in KEY_NAMES}
    return (
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch.object(describe, "_ENV_LOADED", True),
    )


class TestDescribeErrors(unittest.TestCase):
    def test_dead_port_raises_describe_error(self) -> None:
        d = OpenAICompatDescriber(
            base_url="http://127.0.0.1:1/v1/",
            model="x",
            api_key="fake-key-for-test",
            timeout=0.5,
        )
        with self.assertRaises(DescribeError):
            d.describe(system="s", user="u", image_png=b"\x89PNG\r\n\x1a\nxxxx")

    def test_missing_key_is_a_describe_error(self) -> None:
        env, latch = _no_keys()
        with env, latch:
            d = OpenAICompatDescriber(base_url="http://127.0.0.1:1/v1/", model="x")
            with self.assertRaises(DescribeError) as ctx:
                d.describe(system="s", user="u", image_png=b"png")
        self.assertIn("no API key", str(ctx.exception))

    def test_null_describer_returns_nothing_without_network(self) -> None:
        self.assertEqual(NullDescriber().describe(system="s", user="u", image_png=b"png"), "")

    def test_scripted_describer_records_prompts_and_streams_tokens(self) -> None:
        seen: list[str] = []
        describer = ScriptedDescriber(["one two three four five six seven eight"])
        text = describer.describe(system="sys", user="usr", image_png=b"png", on_token=seen.append)
        self.assertEqual(text, "one two three four five six seven eight")
        self.assertGreater(len(seen), 1)  # delivered in chunks, not one blob
        self.assertEqual(describer.calls[0]["system"], "sys")


class TestKeyResolution(unittest.TestCase):
    def test_explicit_key_wins(self) -> None:
        env, latch = _no_keys()
        with env, latch:
            self.assertEqual(describe.resolve_api_key("  explicit  "), "explicit")

    def test_environment_is_used_when_no_explicit_key(self) -> None:
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": " from-env "}, clear=False):
            with mock.patch.object(describe, "_ENV_LOADED", True):
                self.assertEqual(describe.resolve_api_key(None), "from-env")

    def test_blank_explicit_key_means_no_key(self) -> None:
        # `--novel-key ""` is an escape hatch: a blank value disables the environment key on purpose.
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "from-env"}, clear=False):
            with mock.patch.object(describe, "_ENV_LOADED", True):
                self.assertIsNone(describe.resolve_api_key("   "))

    def test_no_key_anywhere_is_none(self) -> None:
        env, latch = _no_keys()
        with env, latch:
            self.assertIsNone(describe.resolve_api_key(None))


if __name__ == "__main__":
    unittest.main()
