"""The sink contract: registration, frame counts, byte sizes, clean errors."""

from __future__ import annotations

import itertools
import pathlib
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streamkit.sink import build_sink, registered_sinks  # noqa: E402
from streamkit.sources.pattern import PatternSource  # noqa: E402


class TestRegistry(unittest.TestCase):
    def test_builtin_sinks_registered(self) -> None:
        for name in ("ansi", "ppm_seq"):
            self.assertIn(name, registered_sinks())

    def test_unknown_sink_lists_the_alternatives(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            build_sink("hologram")
        self.assertIn("ppm_seq", str(ctx.exception))


class TestPpmSeqSink(unittest.TestCase):
    def test_writes_one_exact_file_per_frame(self) -> None:
        width, height, n = 40, 24, 5
        source = PatternSource("bars", width=width, height=height, fps=5)
        with tempfile.TemporaryDirectory() as tmp:
            sink = build_sink("ppm_seq", out_dir=tmp)
            sink.open(width, height)
            for grid in itertools.islice(source.frames(), n):
                sink.write(grid)
            sink.close()

            files = sorted(pathlib.Path(tmp).glob("*.ppm"))
            self.assertEqual(len(files), n)
            self.assertEqual(sink.frames_written, n)
            for path in files:
                raw = path.read_bytes()
                header = f"P6\n{width} {height}\n255\n".encode("ascii")
                self.assertTrue(raw.startswith(header), path.name)
                self.assertEqual(len(raw) - len(header), width * height * 3, path.name)

    def test_frame_names_follow_the_grid_index(self) -> None:
        source = PatternSource("square", width=8, height=8, fps=2)
        with tempfile.TemporaryDirectory() as tmp:
            sink = build_sink("ppm_seq", out_dir=tmp)
            sink.open(8, 8)
            grids = list(itertools.islice(source.frames(), 3))
            for grid in grids:
                sink.write(grid)
            sink.close()
            names = sorted(p.name for p in pathlib.Path(tmp).glob("*.ppm"))
        self.assertEqual(names, ["frame_00000.ppm", "frame_00001.ppm", "frame_00002.ppm"])


class TestSourceContract(unittest.TestCase):
    def test_pattern_source_exposes_geometry_and_meta(self) -> None:
        source = PatternSource("sweep", width=32, height=16, fps=8)
        grid = next(source.frames())
        self.assertEqual((source.width, source.height), (32, 16))
        self.assertEqual((grid.width, grid.height), (32, 16))
        self.assertEqual(grid.meta["source"], "pattern:sweep")
        self.assertEqual(grid.index, 0)

    def test_unknown_pattern_raises(self) -> None:
        with self.assertRaises(ValueError):
            PatternSource("hologram")


if __name__ == "__main__":
    unittest.main()
