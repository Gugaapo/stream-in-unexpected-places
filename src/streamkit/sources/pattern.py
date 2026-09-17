"""Synthetic frame sources: the test harness for the whole project family.

No ffmpeg, no network, no randomness unless asked for. Every pattern is a pure function of
(frame index, width, height, seed), so two runs produce byte-identical frames — which is what
makes every other sink testable, and why the medium briefs can all be verified offline.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from ..grid import Grid

PATTERN_NAMES = ("bars", "square", "sweep", "noise")

_BAR_COLORS = np.array(
    [
        [255, 255, 255],  # white
        [255, 255, 0],  # yellow
        [0, 255, 255],  # cyan
        [0, 255, 0],  # green
        [255, 0, 255],  # magenta
        [255, 0, 0],  # red
        [0, 0, 255],  # blue
    ],
    dtype=np.uint8,
)


class PatternSource:
    """A deterministic synthetic video source."""

    def __init__(
        self,
        name: str = "bars",
        *,
        width: int = 160,
        height: int = 48,
        fps: float = 12.0,
        seed: int = 1234,
    ) -> None:
        key = (name or "").strip().lower()
        if key not in PATTERN_NAMES:
            raise ValueError(f"unknown pattern {name!r}; use {', '.join(PATTERN_NAMES)}")
        if width < 1 or height < 1:
            raise ValueError("width and height must be >= 1")
        if fps <= 0:
            raise ValueError("fps must be > 0")

        self.name = f"pattern:{key}"
        self.pattern = key
        self.width = int(width)
        self.height = int(height)
        self.fps = float(fps)
        self.seed = int(seed)
        self._closed = False

    # ----- Source protocol ---------------------------------------------------
    def frames(self) -> Iterator[Grid]:
        index = 0
        while not self._closed:
            array = self._render(index)
            yield Grid(array, index=index, t=index / self.fps,
                       meta={"source": self.name, "fps": self.fps, "pattern": self.pattern})
            index += 1

    def close(self) -> None:
        self._closed = True

    # ----- pattern implementations ------------------------------------------
    def _render(self, index: int) -> np.ndarray:
        renderer = getattr(self, f"_pattern_{self.pattern}")
        return renderer(index)

    def _pattern_bars(self, index: int) -> np.ndarray:
        """SMPTE-ish 7-bar chart with a grey ramp strip. Static: a stable reference image."""
        w, h = self.width, self.height
        bars_h = max(1, int(h * 0.66))
        img = np.zeros((h, w, 3), dtype=np.uint8)

        n = len(_BAR_COLORS)
        edges = np.linspace(0, w, n + 1).astype(int)
        for i in range(n):
            img[:bars_h, edges[i] : edges[i + 1]] = _BAR_COLORS[i]

        if h > bars_h:
            ramp = np.linspace(0, 255, w, dtype=np.uint8)
            img[bars_h:, :] = ramp[None, :, None]
        return img

    def _pattern_square(self, index: int) -> np.ndarray:
        """One white square travelling diagonally on dark blue. The classic feedback test card."""
        w, h = self.width, self.height
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:, :, 2] = 48

        size = max(2, min(w, h) // 6)
        span_x = max(1, w - size)
        span_y = max(1, h - size)
        # ping-pong so the square never leaves the frame
        bx = index % (2 * span_x)
        by = index % (2 * span_y)
        x = bx if bx <= span_x else 2 * span_x - bx
        y = by if by <= span_y else 2 * span_y - by
        img[y : y + size, x : x + size] = 255
        return img

    def _pattern_sweep(self, index: int) -> np.ndarray:
        """Hue sweeping with a vertical brightness ramp — exercises the sharpest fg/bg splits."""
        w, h = self.width, self.height
        hue = np.linspace(0.0, 1.0, w, dtype=np.float32) + (index / 60.0)
        hue = np.mod(hue, 1.0)
        value = np.linspace(1.0, 0.15, h, dtype=np.float32)[:, None]
        hsv = np.stack(
            [
                np.broadcast_to(hue, (h, w)),
                np.ones((h, w), dtype=np.float32),
                np.broadcast_to(value, (h, w)),
            ],
            axis=-1,
        )
        return np.clip(_hsv_to_rgb(hsv) * 255.0, 0, 255).astype(np.uint8)

    def _pattern_noise(self, index: int) -> np.ndarray:
        """Seeded noise: determinism is per (index, seed)."""
        rng = np.random.default_rng((self.seed, index))
        return rng.integers(0, 256, size=(self.height, self.width, 3), dtype=np.uint8)


def _hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
    """Vectorised HSV->RGB for float arrays in 0..1."""
    h, s, v = hsv[..., 0] * 6.0, hsv[..., 1], hsv[..., 2]
    i = np.floor(h).astype(np.int32)
    f = h - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = np.mod(i, 6)

    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)
