"""Debug/testing sink: write every frame to disk as a binary PPM (stdlib only, no Pillow)."""

from __future__ import annotations

from pathlib import Path

from ..grid import Grid
from ..sink import register


@register("ppm_seq")
class PpmSeqSink:
    def __init__(self, *, out_dir: str = "out/frames", prefix: str = "frame") -> None:
        self.out_dir = Path(out_dir)
        self.prefix = prefix
        self.paths: list[Path] = []
        self.frames_written = 0

    def open(self, width: int, height: int) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def write(self, grid: Grid) -> None:
        path = self.out_dir / f"{self.prefix}_{grid.index:05d}.ppm"
        self.paths.append(grid.save_ppm(path))
        self.frames_written += 1

    def close(self) -> None:
        pass
