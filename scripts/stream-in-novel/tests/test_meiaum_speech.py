"""oMeiaUm transcript parsing — offline, no network."""

from __future__ import annotations

import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.grid import Grid  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402
from stream_in_novel.novel import should_describe  # noqa: E402
from stream_in_novel.speech import parse_live_transcripts, speech_enabled  # noqa: E402


class TestMeiaUmSpeech(unittest.TestCase):
    def test_parse_keeps_final_lines_oldest_first(self) -> None:
        payload = {
            "data": [
                {
                    "id": 3,
                    "text": "Olha lá.",
                    "speaker": {"id": "falante_2", "name": "falante_2"},
                    "is_final": True,
                },
                {
                    "id": 1,
                    "text": "Nossa senhora.",
                    "speaker": {"id": "falante_3", "name": "falante_3"},
                    "is_final": True,
                },
                {"id": 2, "text": "partial", "speaker": {"name": "x"}, "is_final": False},
            ]
        }
        lines = parse_live_transcripts(payload, limit=8)
        self.assertEqual([(line.id, line.text) for line in lines], [(1, "Nossa senhora."), (3, "Olha lá.")])

    def test_auto_only_for_omeiaum(self) -> None:
        self.assertTrue(speech_enabled("auto", "omeiaum"))
        self.assertTrue(speech_enabled("auto", "twitch:meiaum"))
        self.assertFalse(speech_enabled("auto", "gaules"))
        self.assertTrue(speech_enabled("meiaum", "gaules"))
        self.assertFalse(speech_enabled("off", "omeiaum"))

    def test_new_speech_opens_the_change_gate(self) -> None:
        frame = next(PatternSource("bars", width=8, height=8, fps=1).frames())
        same = Grid(frame.rgb.copy(), index=1, t=1.0, meta=dict(frame.meta))
        self.assertFalse(should_describe(frame, same, [], 0, 1.5))
        self.assertTrue(
            should_describe(frame, same, [], 0, 1.5, speech_id=9, last_speech_id=None)
        )
        self.assertFalse(
            should_describe(frame, same, [], 0, 1.5, speech_id=9, last_speech_id=9)
        )


if __name__ == "__main__":
    unittest.main()
