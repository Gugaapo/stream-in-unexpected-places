"""Tests for stdlib .env loading used by the novel API key resolver."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamkit.describe as describe  # noqa: E402


class TestDotenv(unittest.TestCase):
    def setUp(self) -> None:
        describe._ENV_LOADED = False
        self._saved = {
            k: os.environ.pop(k, None)
            for k in ("DEEPSEEK_API_KEY", "NOVEL_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
        }

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        describe._ENV_LOADED = False

    def test_loads_deepseek_key_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / ".env"
            path.write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")
            describe.load_dotenv(path)
            self.assertEqual(describe.resolve_api_key(), "from-dotenv")

    def test_shell_env_wins_over_dotenv(self) -> None:
        os.environ["DEEPSEEK_API_KEY"] = "from-shell"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / ".env"
            path.write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")
            describe.load_dotenv(path)
            self.assertEqual(describe.resolve_api_key(), "from-shell")


if __name__ == "__main__":
    unittest.main()
