"""The Grid: one RGB frame at a chosen resolution, plus the resamplers sinks rely on."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RESIZE_METHODS = ("area", "nearest")


@dataclass
class Grid:
    """An RGB24 frame held as a uint8 array of shape (height, width, 3).

    ``index`` is the frame counter, ``t`` a monotonic source timestamp (seconds) and ``meta``
    carries sink-agnostic extras (channel name, page number, fps, ...).
    """

    rgb: np.ndarray
    index: int = 0
    t: float = 0.0
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        arr = np.asarray(self.rgb)
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise ValueError(f"rgb must have shape (h, w, 3), got {arr.shape}")
        if arr.shape[0] < 1 or arr.shape[1] < 1:
            raise ValueError("rgb must be at least 1x1")
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        self.rgb = np.ascontiguousarray(arr)

    # ----- basics -----------------------------------------------------------
    @property
    def width(self) -> int:
        return int(self.rgb.shape[1])

    @property
    def height(self) -> int:
        return int(self.rgb.shape[0])

    @property
    def rgb_bytes(self) -> bytes:
        """Raw RGB24 bytes, row-major — the format the terminal renderer and ffmpeg expect."""
        return self.rgb.tobytes()

    @classmethod
    def from_raw(
        cls,
        raw: bytes | bytearray | memoryview,
        width: int,
        height: int,
        *,
        index: int = 0,
        t: float = 0.0,
        meta: dict | None = None,
    ) -> Grid:
        expected = width * height * 3
        if len(raw) < expected:
            raise ValueError(f"raw buffer is {len(raw)} bytes, need {expected} for {width}x{height}")
        arr = np.frombuffer(bytes(raw[:expected]), dtype=np.uint8).reshape(height, width, 3)
        return cls(arr, index=index, t=t, meta=dict(meta or {}))

    def copy(self) -> Grid:
        return Grid(self.rgb.copy(), index=self.index, t=self.t, meta=dict(self.meta))

    def with_index(self, index: int, t: float | None = None) -> Grid:
        return Grid(self.rgb, index=index, t=self.t if t is None else t, meta=self.meta)

    # ----- resampling -------------------------------------------------------
    def resize(self, width: int, height: int, method: str = "area") -> Grid:
        """Resample to ``width`` x ``height``.

        ``nearest`` reproduces the historical stream-in-terminal sampler exactly
        (``x_src = x * src_w // dst_w``), which keeps the terminal output byte-identical.
        ``area`` is a box-area average — the right default for video, since it does not alias.
        """
        if method not in RESIZE_METHODS:
            raise ValueError(f"unknown resize method {method!r}; use {RESIZE_METHODS}")
        width, height = int(width), int(height)
        if width < 1 or height < 1:
            raise ValueError("dimensions must be >= 1")
        if (width, height) == (self.width, self.height):
            return self
        if method == "nearest":
            return Grid(
                _resize_nearest(self.rgb, width, height),
                index=self.index,
                t=self.t,
                meta=self.meta,
            )
        return Grid(
            _resize_area(self.rgb, width, height), index=self.index, t=self.t, meta=self.meta
        )

    # ----- misc -------------------------------------------------------------
    def save_ppm(self, path: str | Path) -> Path:
        """Write a binary P6 PPM. Stdlib only, so tests never need Pillow."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        header = f"P6\n{self.width} {self.height}\n255\n".encode("ascii")
        with p.open("wb") as fh:
            fh.write(header)
            fh.write(self.rgb_bytes)
        return p

    def mean_abs_error(self, other: Grid) -> float:
        """Mean absolute per-channel difference against another equally sized grid."""
        if (self.width, self.height) != (other.width, other.height):
            raise ValueError("grids must have equal dimensions")
        return float(
            np.abs(self.rgb.astype(np.int16) - other.rgb.astype(np.int16)).mean()
        )


def _resize_nearest(src: np.ndarray, dst_w: int, dst_h: int) -> np.ndarray:
    src_h, src_w = src.shape[0], src.shape[1]
    ys = (np.arange(dst_h) * src_h) // dst_h
    xs = (np.arange(dst_w) * src_w) // dst_w
    return np.ascontiguousarray(src[ys][:, xs])


def _box_weights(src_n: int, dst_n: int) -> np.ndarray:
    """Exact box-filter weights (dst_n x src_n) for mapping src_n samples onto dst_n bins."""
    edges = np.linspace(0.0, float(src_n), dst_n + 1)
    weights = np.zeros((dst_n, src_n), dtype=np.float32)
    for i in range(dst_n):
        lo, hi = edges[i], edges[i + 1]
        span = hi - lo
        first = int(np.floor(lo))
        last = min(int(np.ceil(hi)), src_n)
        for j in range(first, last):
            overlap = min(hi, j + 1.0) - max(lo, float(j))
            if overlap > 0.0:
                weights[i, j] = overlap / span
    return weights


def _resize_area(src: np.ndarray, dst_w: int, dst_h: int) -> np.ndarray:
    src_h, src_w = src.shape[0], src.shape[1]
    wx = _box_weights(src_w, dst_w)  # (dst_w, src_w)
    wy = _box_weights(src_h, dst_h)  # (dst_h, src_h)
    work = src.astype(np.float32)
    # average along x, then along y: both are matrix products, fully vectorised
    tmp = np.tensordot(wx, work, axes=([1], [1]))  # (dst_w, src_h, 3)
    out = np.tensordot(wy, tmp, axes=([1], [1]))  # (dst_h, dst_w, 3)
    # floor(x + 0.5), not np.rint: rint rounds halves to even, which makes e.g. a quadrant mean of
    # 2.5 come out as 2 — surprising for image data and for anyone reading the tests.
    return np.clip(np.floor(out + 0.5), 0, 255).astype(np.uint8)
