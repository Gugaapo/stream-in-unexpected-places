"""The streamkit CLI — run any source into any registered sink.

    streamkit --source pattern:bars --size 80x24 --sink ansi --seconds 5
    streamkit --source twitch:oMeiaUm --size 160x48 --fps 12 --sink ansi
    streamkit --list-sinks

This module is also the shared CLI toolkit for medium projects (see ``scripts/`` in the repo). A
medium's own CLI is usually just its flags plus four calls:

    from streamkit.cli import (add_core_arguments, build_source_from_args, open_source,
                               run_pipeline_from_args)

    parser = argparse.ArgumentParser(prog="stream-in-thing")
    add_core_arguments(parser)
    ...add the medium's own flags...
    args = parser.parse_args()
    return run_pipeline_from_args(args, sink_name="thing", sink_kwargs=lambda label: {...},
                                 prog="stream-in-thing")
"""

from __future__ import annotations

import argparse
import re
import sys

from . import sinks as _sinks  # noqa: F401  (registration side effect for the built-in sinks)
from .ffmpeg import FfmpegNotFound
from .pipeline import PACE_MODES, run
from .sink import build_sink, registered_sinks
from .sources import PATTERN_NAMES, build_source
from .sources.twitch import StreamResolveError

__all__ = [
    "add_core_arguments",
    "build_parser",
    "build_source_from_args",
    "main",
    "open_source",
    "parse_size",
    "run_pipeline_from_args",
]

SIZE_RE = re.compile(r"^\s*(\d+)\s*[x×]\s*(\d+)\s*$")


def parse_size(value: str) -> tuple[int, int]:
    """``160x48`` (also accepts the multiplication sign) → ``(160, 48)``."""
    match = SIZE_RE.match(value or "")
    if not match:
        raise argparse.ArgumentTypeError(f"expected WxH (e.g. 160x48), got {value!r}")
    width, height = int(match.group(1)), int(match.group(2))
    if width < 1 or height < 1:
        raise argparse.ArgumentTypeError("size must be >= 1x1")
    return width, height


def add_core_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the arguments every medium shares: source, geometry, pacing, limits, output."""
    parser.add_argument("--source", default="pattern:bars",
                        help="twitch:<channel> | file:<path> | url:<url> | pattern:<%s>"
                             % "|".join(PATTERN_NAMES))
    parser.add_argument("--size", type=parse_size, default=(160, 48),
                        help="decode grid, WxH (default 160x48)")
    parser.add_argument("--fps", type=float, default=12.0, help="target frames per second")
    parser.add_argument("--quality", default="best",
                        help="stream quality for twitch sources (best/worst/1080p/720p/480p/160p)")
    parser.add_argument("--seed", type=int, default=1234, help="pattern source seed")
    parser.add_argument("--ffmpeg", dest="ffmpeg_path", default=None, help="explicit ffmpeg binary")
    parser.add_argument("--out", default=None, help="sink output path (sink-specific)")
    parser.add_argument("--seconds", type=float, default=None, help="stop after N seconds of frames")
    parser.add_argument("--frames", type=int, default=None, help="stop after N frames")
    parser.add_argument("--pace", choices=PACE_MODES, default="realtime",
                        help="realtime sleeps to hold the target fps; fast runs flat out (tests)")
    parser.add_argument("--quiet", action="store_true", help="suppress the closing summary line")
    return parser


def build_source_from_args(args: argparse.Namespace):
    """Build the source described by the core arguments (not yet opened)."""
    width, height = args.size
    return build_source(
        args.source,
        width=width,
        height=height,
        fps=args.fps,
        quality=args.quality,
        seed=args.seed,
        ffmpeg_path=args.ffmpeg_path,
    )


def open_source(source) -> None:
    """Open a source if it needs it (Twitch resolution, ffmpeg spawn). Raises on failure."""
    opener = getattr(source, "open", None)
    if callable(opener):
        opener()


def run_pipeline_from_args(
    args: argparse.Namespace,
    *,
    sink_name: str,
    sink_kwargs=None,
    prog: str = "streamkit",
) -> int:
    """The standard CLI flow: source → sink → :func:`streamkit.pipeline.run` → summary line.

    ``sink_kwargs`` is either a mapping or a callable that receives the opened source and returns the
    sink's constructor kwargs — the usual way to pass a label (``source.name``) or the Twitch channel
    (``streamkit.sources.chat_channel(source)``).
    Returns a process exit code.
    """
    source = build_source_from_args(args)
    try:
        open_source(source)
    except (StreamResolveError, FfmpegNotFound, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    kwargs = sink_kwargs(source) if callable(sink_kwargs) else dict(sink_kwargs or {})
    try:
        sink = build_sink(sink_name, **kwargs)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        source.close()
        return 2

    sink.open(source.width, source.height)
    result = run(
        source,
        sink,
        fps=args.fps,
        pace=args.pace,
        seconds=args.seconds,
        frames=args.frames,
    )
    if result.interrupted:
        print("\ninterrupted", file=sys.stderr)
    if not getattr(args, "quiet", False):
        target = getattr(sink, "path", None)
        if target is None:
            target = getattr(sink, "out_dir", None)
        detail = f" -> {target}" if target is not None else ""
        print(
            f"{prog}: {result.frames} frames in {result.seconds:.2f}s "
            f"({result.fps:.1f} fps) via {sink_name}{detail}",
            file=sys.stderr,
        )
    return 0


def _builtin_sink_options(args: argparse.Namespace, source) -> tuple[str, dict]:
    """Sink kwargs for the sinks that ship with the library."""
    name = args.sink
    if name == "ansi":
        return name, {
            "mode": args.mode,
            "charset": args.chars,
            "color": not args.no_color,
            "truecolor": True if args.truecolor else None,
            "label": source.name,
            "fps": args.fps,
        }
    if name == "ppm_seq":
        return name, {"out_dir": args.out or "out/frames"}
    return name, {}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="streamkit",
        description="Play a source into a medium: source -> grid -> sink.",
    )
    add_core_arguments(p)
    p.add_argument("--sink", default="ansi",
                   help="sink name (see --list-sinks); built in: ansi, ppm_seq")
    # ansi sink
    p.add_argument("--mode", default="compact", choices=("compact", "blocks", "ascii"),
                   help="terminal render mode (ansi sink)")
    p.add_argument("--chars", default=None, help="charset for --mode ascii")
    p.add_argument("--no-color", action="store_true", help="grayscale/block-density rendering")
    p.add_argument("--truecolor", action="store_true", help="force 24-bit ANSI colour")
    p.add_argument("--list-sinks", action="store_true")
    p.add_argument("--list-sources", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_sinks:
        print("\n".join(registered_sinks()))
        return 0
    if args.list_sources:
        print("\n".join(f"pattern:{n}" for n in PATTERN_NAMES))
        print("file:<path>")
        print("url:<url>")
        print("twitch:<channel>")
        return 0

    return run_pipeline_from_args(
        args,
        sink_name=args.sink,
        sink_kwargs=lambda source: _builtin_sink_options(args, source)[1],
        prog="streamkit",
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
