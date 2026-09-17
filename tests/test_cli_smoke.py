"""Offline end-to-end: the CLI must run a pattern into a sink with no ffmpeg on PATH.

Deliberately runs with a PATH that contains no ffmpeg, proving the pattern path is self-contained
(which is what makes the whole test suite runnable inside WSL, where ffmpeg does not exist).
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def run_cli(args: list[str], *, cwd: pathlib.Path, no_ffmpeg_path: bool = False):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    # Windows pipes default to a legacy code page; half-block / sextant output needs UTF-8.
    env["PYTHONIOENCODING"] = "utf-8"
    if no_ffmpeg_path:
        env["PATH"] = os.pathsep.join(
            p for p in env.get("PATH", "").split(os.pathsep) if "ffmpeg" not in p.lower()
        )
        env.pop("FFMPEG_PATH", None)
    return subprocess.run(
        [sys.executable, "-m", "streamkit", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


class TestCliSmoke(unittest.TestCase):
    def test_pattern_to_ppm_seq_counts_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli(
                [
                    "--source", "pattern:bars",
                    "--size", "40x24",
                    "--fps", "5",
                    "--sink", "ppm_seq",
                    "--out", tmp,
                    "--seconds", "2",
                    "--pace", "fast",
                ],
                cwd=REPO,
                no_ffmpeg_path=True,
            )
            frames = sorted(pathlib.Path(tmp).glob("*.ppm"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(frames), 10)  # 2 seconds at 5 fps
        self.assertIn("10 frames", proc.stderr)

    def test_ansi_sink_runs_without_ffmpeg(self) -> None:
        proc = run_cli(
            [
                "--source", "pattern:sweep",
                "--size", "40x24",
                "--fps", "10",
                "--sink", "ansi",
                "--seconds", "0.3",
                "--pace", "fast",
            ],
            cwd=REPO,
            no_ffmpeg_path=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("\x1b[H", proc.stdout)

    def test_list_sinks(self) -> None:
        proc = run_cli(["--list-sinks"], cwd=REPO)
        self.assertEqual(proc.returncode, 0)
        for name in ("ansi", "ppm_seq"):
            self.assertIn(name, proc.stdout)

    def test_bad_sink_fails_cleanly(self) -> None:
        proc = run_cli(
            ["--source", "pattern:bars", "--size", "8x8", "--sink", "hologram"],
            cwd=REPO,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("unknown sink", proc.stderr)
        self.assertIn("ansi", proc.stderr)  # the error lists what is available

    def test_bad_source_spec_fails_cleanly(self) -> None:
        proc = run_cli(
            ["--source", "pattern:hologram", "--size", "8x8", "--sink", "ppm_seq",
             "--out", tempfile.gettempdir()],
            cwd=REPO,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unknown pattern", proc.stderr)


if __name__ == "__main__":
    unittest.main()
