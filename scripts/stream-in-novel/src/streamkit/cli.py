"""streamkit CLI — one command for every source/sink combination.

    python -m streamkit --source pattern:bars --size 640x360 --sink novel --seconds 30
    python -m streamkit --source twitch:oMeiaUm --size 640x360 --sink novel_txt --out novel.md

Ctrl+C stops cleanly and finalises any open sink.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

from . import sinks as _sinks  # noqa: F401  (registration side effect)
from .ffmpeg import FfmpegNotFound
from .sink import build_sink, registered_sinks
from .sources import PATTERN_NAMES, build_source
from .sources.twitch import StreamResolveError

SIZE_RE = re.compile(r"^\s*(\d+)\s*[x×]\s*(\d+)\s*$")


def parse_size(value: str) -> tuple[int, int]:
    match = SIZE_RE.match(value or "")
    if not match:
        raise argparse.ArgumentTypeError(f"expected WxH (e.g. 160x48), got {value!r}")
    width, height = int(match.group(1)), int(match.group(2))
    if width < 1 or height < 1:
        raise argparse.ArgumentTypeError("size must be >= 1x1")
    return width, height


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="streamkit",
        description="Play a source into any medium: source -> grid -> sink.",
    )
    p.add_argument("--source", default="pattern:bars",
                   help="twitch:<channel> | file:<path> | pattern:<%s>" % "|".join(PATTERN_NAMES))
    p.add_argument("--size", type=parse_size, default=(160, 48),
                   help="decode grid, WxH (default 160x48)")
    p.add_argument("--fps", type=float, default=12.0, help="target frames per second")
    p.add_argument("--sink", default="ansi", help="sink name (see --list-sinks)")
    p.add_argument("--out", default=None,
                   help="transcript path for the novel sinks (default out/novel/<channel>-<date>.md) "
                        "or a directory for ppm_seq")
    p.add_argument("--quality", default="best",
                   help="stream quality for twitch sources (best/worst/1080p/720p/480p/160p)")
    p.add_argument("--mode", default="compact", choices=("compact", "blocks", "ascii"),
                   help="terminal render mode (ansi sink)")
    p.add_argument("--chars", default=None, help="charset for --mode ascii")
    p.add_argument("--no-color", action="store_true", help="grayscale/block-density rendering")
    p.add_argument("--truecolor", action="store_true", help="force 24-bit ANSI colour")
    p.add_argument("--seconds", type=float, default=None, help="stop after N seconds of frames")
    p.add_argument("--frames", type=int, default=None, help="stop after N frames")
    p.add_argument("--pace", choices=("realtime", "fast"), default="realtime",
                   help="realtime sleeps to hold the target fps; fast runs flat out (tests)")
    p.add_argument("--seed", type=int, default=1234, help="pattern source seed")
    p.add_argument("--ffmpeg", dest="ffmpeg_path", default=None, help="explicit ffmpeg binary")
    p.add_argument("--quiet", action="store_true", help="suppress the ansi sink's output")
    # Novel (prose) options — DeepSeek OpenAI-compat by default
    p.add_argument("--novel-interval", type=float, default=15.0,
                   help="novel: seconds between model calls (default 15)")
    p.add_argument("--novel-change-threshold", type=float, default=1.5,
                   help="novel: mean-abs-error gate; skip near-identical frames (default 1.5)")
    p.add_argument("--novel-style", choices=("dumb", "novel", "nature", "noir"), default="dumb",
                   help="novel: persona preset (default dumb = snarky + precise)")
    p.add_argument("--novel-lang", choices=("pt-BR", "en", "auto"), default="pt-BR",
                   help="novel: output language (default pt-BR)")
    p.add_argument("--novel-no-chat", action="store_true",
                   help="novel: ignore Twitch chat")
    p.add_argument("--novel-base-url", default="https://api.deepseek.com",
                   help="novel: OpenAI-compatible base URL (default DeepSeek)")
    p.add_argument("--novel-model", default="deepseek-v4-flash-vision-exp",
                   help="novel: vision model id (default deepseek-v4-flash-vision-exp)")
    p.add_argument("--novel-key", default=None,
                   help="novel: API key (else DEEPSEEK_API_KEY / NOVEL_API_KEY)")
    p.add_argument("--novel-describer", choices=("openai", "scripted", "null"), default="openai",
                   help="novel: describer backend (scripted/null = offline)")
    p.add_argument("--list-sinks", action="store_true")
    p.add_argument("--list-sources", action="store_true")
    return p


def _chat_channel_from_source(source_spec: str) -> str | None:
    spec = (source_spec or "").strip()
    if spec.startswith("twitch:"):
        return spec.split(":", 1)[1].lower() or None
    return None


def _sink_options(args: argparse.Namespace, label: str) -> tuple[str, dict]:
    name = args.sink
    if name == "ansi":
        return name, {
            "mode": args.mode,
            "charset": args.chars,
            "color": not args.no_color,
            "truecolor": True if args.truecolor else None,
            "label": label,
            "fps": args.fps,
        }
    if name == "ppm_seq":
        return name, {"out_dir": args.out or "out/frames"}
    if name in ("novel", "novel_txt"):
        return name, {
            "interval": args.novel_interval,
            "change_threshold": args.novel_change_threshold,
            "style": args.novel_style,
            "lang": args.novel_lang,
            "no_chat": args.novel_no_chat,
            "chat_channel": None if args.novel_no_chat else _chat_channel_from_source(args.source),
            "out_path": args.out,
            "base_url": args.novel_base_url,
            "model": args.novel_model,
            "api_key": args.novel_key,
            "describer": args.novel_describer,
            "color": not args.no_color,
            "label": label,
        }
    return name, {}


def main(argv: list[str] | None = None) -> int:
    from .describe import load_dotenv

    load_dotenv()
    args = build_parser().parse_args(argv)

    if args.list_sinks:
        print("\n".join(registered_sinks()))
        return 0
    if args.list_sources:
        print("\n".join(f"pattern:{n}" for n in PATTERN_NAMES))
        print("file:<path>")
        print("twitch:<channel>")
        return 0

    width, height = args.size
    source = build_source(
        args.source,
        width=width,
        height=height,
        fps=args.fps,
        quality=args.quality,
        seed=args.seed,
        ffmpeg_path=args.ffmpeg_path,
    )

    opener = getattr(source, "open", None)
    if callable(opener):
        try:
            opener()
        except (StreamResolveError, FfmpegNotFound, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    sink_name, sink_kwargs = _sink_options(args, source.name)
    sink = build_sink(sink_name, **sink_kwargs)
    sink.open(source.width, source.height)

    max_frames = args.frames
    if args.seconds is not None:
        seconds_frames = int(round(args.seconds * args.fps))
        max_frames = seconds_frames if max_frames is None else min(max_frames, seconds_frames)

    written = 0
    started = time.monotonic()
    deadline = started
    try:
        for grid in source.frames():
            sink.write(grid)
            written += 1
            if max_frames is not None and written >= max_frames:
                break
            if args.pace == "realtime":
                deadline += 1.0 / args.fps
                delay = deadline - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
    finally:
        sink.close()
        source.close()

    elapsed = time.monotonic() - started
    detail = ""
    target = getattr(sink, "path", None)
    if target is not None:
        detail = f" -> {target}"
    elif getattr(sink, "out_dir", None) is not None:
        detail = f" -> {sink.out_dir}"
    print(
        f"streamkit: {written} frames in {elapsed:.2f}s "
        f"({written / elapsed if elapsed else 0:.1f} fps) via {sink_name}{detail}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
