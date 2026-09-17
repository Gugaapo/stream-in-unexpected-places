"""Source-spec dispatch: every spec form must map to the right source class, with no network."""

from __future__ import annotations

import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.sources import build_source  # noqa: E402
from streamkit.sources.live import FileSource, TwitchSource, UrlSource  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402


class TestSourceDispatch(unittest.TestCase):
    def test_pattern_specs(self) -> None:
        source = build_source("pattern:bars", width=20, height=10)
        self.assertIsInstance(source, PatternSource)
        self.assertEqual(source.name, "pattern:bars")

    def test_file_spec(self) -> None:
        source = build_source("file:clip.mp4")
        self.assertIsInstance(source, FileSource)
        self.assertEqual(source.path, "clip.mp4")
        self.assertTrue(source.name.startswith("file:"))

    def test_url_specs_do_not_go_through_the_twitch_resolver(self) -> None:
        for spec in ("url:https://example.com/a.m3u8", "https://example.com/a.m3u8"):
            with self.subTest(spec=spec):
                source = build_source(spec)
                self.assertIsInstance(source, UrlSource)
                self.assertEqual(source.url, "https://example.com/a.m3u8")

    def test_twitch_specs(self) -> None:
        for spec in ("twitch:someone", "someone", "https://twitch.tv/someone", "twitch.tv/someone"):
            with self.subTest(spec=spec):
                source = build_source(spec)
                self.assertIsInstance(source, TwitchSource)
                self.assertEqual(source.channel, "someone")
                self.assertFalse(source.frames_yielded)

    def test_empty_spec_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_source("   ")


if __name__ == "__main__":
    unittest.main()
