"""Regression: the terminal renderer's exact bytes are pinned.

These digests were captured from the renderer as it shipped in live-in-terminal and then streamkit,
before the library was split out of this repository (2026-09-17). The renderer is the one piece of
this library whose output people see in a terminal, so any change to a single escape byte — colour
downgrade, resampling, half-block choice — fails here on purpose.

If a digest must change, that is a rendering change: say so in the commit message and update the
numbers here, never "just make the test pass".
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.render.terminal import RenderMode, render_frame, resize_rgb  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402

DECODE = (40, 24)
PIXELS = (80, 48)

# pattern:square, first frame, resampled 40x24 -> 80x48
FRAME_RGB_SHA = "28e38f68845711b8277594396882e78a9f160568e7fe64bf76a9114d28d1dfd6"
RESIZED_SHA = "5a4ac0633db7c5f3e494c76a4e4ea69b3cbb3fbccb900bff3527a3593eb32371"

# sha256 of the rendered text; (length, digest)
RENDERED = {
    ("compact", True, True): (2807, "8a5633df490c7479bc0775ab6e4898992a4431c83927d26e6cb617f4b7963d00"),
    ("compact", True, False): (2551, "ab129005d465b1d757a3be313cf23d09cb130a250c9472b00cd318ef6800f47e"),
    ("compact", False, False): (1943, "42bdb0d1d6d487d7730613ddf9caba6f5bca79d3c7dec1d639d2f96a5062b238"),
    ("blocks", True, True): (8743, "0d16ed0cce9bfb1c11b7e5104a063bfec8fc35f86e9f88c340b09b048cbb4917"),
    ("blocks", True, False): (8487, "b3796fb4a34199c18b091559627add46299eb0c193b9a5fe6b8e82eb51778351"),
    ("blocks", False, False): (7727, "45bb495a6dd5f8d43c72a6bc33bbaf6a441141a62a829a6aab1fd5a9530f8153"),
    ("ascii", True, True): (58159, "9276a01ff7f9d71c87bf9d33e66b2837cc341dcdf05748b78d67327d061c1c7e"),
    ("ascii", True, False): (3887, "0fc726c8c249ff2f00250385e109c6dbb7443718798c10b805b9e85a8d9c3fd7"),
    ("ascii", False, False): (3887, "0fc726c8c249ff2f00250385e109c6dbb7443718798c10b805b9e85a8d9c3fd7"),
}


def _frame() -> tuple[bytes, bytes]:
    source = PatternSource("square", width=DECODE[0], height=DECODE[1], fps=6)
    rgb = next(source.frames()).rgb_bytes
    return rgb, resize_rgb(rgb, DECODE[0], DECODE[1], PIXELS[0], PIXELS[1])


class TestRendererGolden(unittest.TestCase):
    def test_source_frame_and_resampler_are_stable(self) -> None:
        rgb, resized = _frame()
        self.assertEqual(hashlib.sha256(rgb).hexdigest(), FRAME_RGB_SHA)
        self.assertEqual(hashlib.sha256(resized).hexdigest(), RESIZED_SHA)
        self.assertEqual(len(resized), PIXELS[0] * PIXELS[1] * 3)

    def test_every_mode_and_colour_depth_matches_the_golden_bytes(self) -> None:
        _, resized = _frame()
        for (mode, color, truecolor), (length, digest) in RENDERED.items():
            with self.subTest(mode=mode, color=color, truecolor=truecolor):
                art = render_frame(
                    resized,
                    PIXELS[0],
                    PIXELS[1],
                    mode=RenderMode(mode),
                    chars="classic",
                    color=color,
                    truecolor=truecolor,
                )
                self.assertEqual(len(art), length)
                self.assertEqual(hashlib.sha256(art.encode("utf-8")).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
