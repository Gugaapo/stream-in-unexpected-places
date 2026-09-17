"""Run a source into a sink — the loop every medium shares.

A medium normally does not write this loop itself: build a source with
:func:`streamkit.sources.build_source`, build a sink with :func:`streamkit.sink.build_sink`, then
hand both to :func:`run`. Pacing, frame limits, Ctrl+C and closing are handled here.

Example::

    from streamkit.pipeline import run
    from streamkit.sink import build_sink
    from streamkit.sources import build_source

    source = build_source("twitch:oMeiaUm", width=160, height=48, fps=12)
    source.open()                       # resolves the stream; raises StreamResolveError
    sink = build_sink("ansi", mode="blocks")
    sink.open(source.width, source.height)
    result = run(source, sink, fps=12, seconds=30)
    print(result.frames, "frames", f"{result.fps:.1f} fps")
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .sink import Sink
from .sources import Source

__all__ = ["RunResult", "frame_limit", "run"]

PACE_MODES = ("realtime", "fast")


@dataclass
class RunResult:
    """What a run did."""

    frames: int = 0
    seconds: float = 0.0
    interrupted: bool = False

    @property
    def fps(self) -> float:
        return self.frames / self.seconds if self.seconds else 0.0


def frame_limit(*, fps: float, seconds: float | None, frames: int | None) -> int | None:
    """Combine a time limit and a frame limit into one frame count (``None`` = no limit)."""
    if seconds is None:
        return frames
    from_seconds = int(round(float(seconds) * float(fps)))
    if frames is None:
        return from_seconds
    return min(int(frames), from_seconds)


def run(
    source: Source,
    sink: Sink,
    *,
    fps: float = 12.0,
    pace: str = "realtime",
    seconds: float | None = None,
    frames: int | None = None,
) -> RunResult:
    """Feed ``source`` into ``sink`` until the limit, the stream end, or Ctrl+C.

    ``pace="realtime"`` sleeps to hold the target ``fps``; ``pace="fast"`` runs flat out (tests and
    recording, where the output's duration comes from its metadata rather than wall time).
    Both the sink and the source are closed on every path, including errors and interrupts — an
    in-progress file is finalised.
    """
    if pace not in PACE_MODES:
        raise ValueError(f"unknown pace {pace!r}; expected one of {', '.join(PACE_MODES)}")

    limit = frame_limit(fps=fps, seconds=seconds, frames=frames)
    result = RunResult()
    started = time.monotonic()
    deadline = started
    try:
        for grid in source.frames():
            sink.write(grid)
            result.frames += 1
            if limit is not None and result.frames >= limit:
                break
            if pace == "realtime":
                deadline += 1.0 / float(fps)
                delay = deadline - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
    except KeyboardInterrupt:
        result.interrupted = True
    finally:
        result.seconds = time.monotonic() - started
        sink.close()
        source.close()
    return result
