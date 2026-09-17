"""The real decode path, end to end, without the network: a local file through ffmpeg.

Skipped when ffmpeg is unavailable (e.g. inside WSL), which is why every other test is ffmpeg-free.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.ffmpeg import find_ffmpeg, has_ffmpeg  # noqa: E402
from streamkit.sources import build_source  # noqa: E402


def make_test_clip(path: pathlib.Path, *, seconds: int = 2, fps: int = 10) -> None:
    subprocess.run(
        [
            find_ffmpeg(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc2=size=64x36:rate={fps}",
            "-t", str(seconds), "-pix_fmt", "yuv420p", "-y", str(path),
        ],
        check=True,
        capture_output=True,
    )


@unittest.skipUnless(has_ffmpeg(), "ffmpeg not available on this machine")
class TestFileSource(unittest.TestCase):
    def test_decodes_a_local_file_into_grids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clip = pathlib.Path(tmp) / "clip.mp4"
            make_test_clip(clip, seconds=2, fps=10)
            source = build_source(f"file:{clip}", width=64, height=36, fps=10)
            source.open()
            frames = []
            try:
                for grid in source.frames():
                    frames.append(grid)
                    if len(frames) >= 20:
                        break
            finally:
                source.close()

        self.assertGreaterEqual(len(frames), 10)
        self.assertLessEqual(len(frames), 20)
        first = frames[0]
        self.assertEqual((first.width, first.height), (64, 36))
        self.assertEqual(first.rgb.shape, (36, 64, 3))
        self.assertEqual(frames[0].rgb_bytes, frames[0].rgb_bytes)
        # a real decode must not be a blank frame
        self.assertGreater(int(frames[0].rgb.max()), 0)


if __name__ == "__main__":
    unittest.main()
