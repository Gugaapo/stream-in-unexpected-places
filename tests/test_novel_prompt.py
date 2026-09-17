"""Acceptance: prompt assembly is pure and style/lang aware."""

from __future__ import annotations

import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.novel import StoryState, build_prompt, is_streamer_user  # noqa: E402


class TestNovelPrompt(unittest.TestCase):
    def test_tail_keeps_last_three_and_chat_usernames(self) -> None:
        state = StoryState()
        for p in ("P1 old", "P2", "P3", "P4 newest-but-one", "P5 newest"):
            state.add(p)
        chat = [(f"user{i}", f"line{i}") for i in range(10)]
        system, user = build_prompt(state, chat, "novel", "pt-BR", "gaules")
        self.assertIn("P3", user)
        self.assertIn("P4 newest-but-one", user)
        self.assertIn("P5 newest", user)
        self.assertNotIn("P1 old", user)
        self.assertNotIn("\nP2\n", "\n" + user + "\n")
        # last 8 chat lines
        self.assertNotIn("user0:", user)
        self.assertNotIn("user1:", user)
        self.assertIn("[CHAT] user2:", user)
        self.assertIn("[CHAT] user9:", user)
        self.assertIn("line9", user)
        self.assertIn("Brazilian Portuguese", system)
        self.assertIn("literary novel", system.lower())
        self.assertIn("gaules", system)
        self.assertIn("anti-hallucination", system.lower())
        self.assertIn("viewer count", system.lower())
        self.assertIn("omit it entirely", system.lower())

    def test_lang_and_style_differ(self) -> None:
        state = StoryState()
        state.add("Once upon a stream.")
        sys_pt, _ = build_prompt(state, [], "novel", "pt-BR", "ch")
        sys_en, _ = build_prompt(state, [], "novel", "en", "ch")
        self.assertNotEqual(sys_pt, sys_en)
        self.assertIn("English", sys_en)

        sys_novel, _ = build_prompt(state, [], "novel", "en", "ch")
        sys_noir, _ = build_prompt(state, [], "noir", "en", "ch")
        self.assertNotEqual(sys_novel, sys_noir)
        self.assertIn("hard-boiled", sys_noir.lower())
        self.assertIn("second person", sys_noir.lower())

        sys_dumb, _ = build_prompt(state, [], "dumb", "en", "ch")
        self.assertNotEqual(sys_dumb, sys_novel)
        self.assertIn("snarky", sys_dumb.lower())

    def test_default_style_is_dumb(self) -> None:
        state = StoryState()
        system, _ = build_prompt(state, [], "nope", "en", "ch")
        self.assertIn("snarky", system.lower())

    def test_streamer_chat_tagged_separately(self) -> None:
        self.assertTrue(is_streamer_user("1e16", "twitch:1e16"))
        self.assertTrue(is_streamer_user("1E16", "1e16"))
        self.assertFalse(is_streamer_user("alice", "1e16"))

        state = StoryState()
        chat = [
            ("1e16", "mds"),
            ("viewer42", "lol"),
            ("Alice", "hi"),
        ]
        _, user = build_prompt(state, chat, "dumb", "pt-BR", "twitch:1e16")
        self.assertIn("[STREAMER] 1e16: mds", user)
        self.assertIn("[CHAT] viewer42: lol", user)
        self.assertIn("[CHAT] Alice: hi", user)
        self.assertNotIn("Falko", user)


if __name__ == "__main__":
    unittest.main()
