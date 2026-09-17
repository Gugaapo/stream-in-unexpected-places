"""stream-in-novel CLI — the stream narrated as prose.

    stream-in-novel --source twitch:oMeiaUm --size 640x360 --fps 2 --sink novel --seconds 180
    stream-in-novel --source pattern:noise --size 640x360 --fps 2 --sink novel_txt \
        --novel-describer scripted --novel-no-chat --seconds 10 --pace fast

Sources, geometry, pacing and limits come from :func:`streamkit.cli.add_core_arguments`; everything
``--novel-*`` is this medium's own.
"""

from __future__ import annotations

import argparse
import sys

from streamkit.cli import add_core_arguments, run_pipeline_from_args
from streamkit.describe import DEFAULT_BASE_URL, DEFAULT_MODEL, load_dotenv
from streamkit.sources import Source, chat_channel

from . import sinks as _sinks  # noqa: F401  (registration side effect)
from .novel import LANGS, STYLES

SINKS = ("novel", "novel_txt")
DESCRIBERS = ("openai", "scripted", "null")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stream-in-novel",
        description="Play a live stream into prose: every interval, a vision model narrates a still.",
    )
    add_core_arguments(p)
    p.add_argument("--sink", default="novel", choices=SINKS,
                   help="novel (ANSI live view) or novel_txt (plain text)")
    p.add_argument("--novel-interval", type=float, default=15.0,
                   help="seconds between model calls (default 15)")
    p.add_argument("--novel-change-threshold", type=float, default=1.5,
                   help="mean-abs-error gate; skip near-identical frames (default 1.5)")
    p.add_argument("--novel-style", choices=STYLES, default="dumb",
                   help="persona preset (default dumb = snarky + precise)")
    p.add_argument("--novel-lang", choices=LANGS, default="pt-BR",
                   help="output language (default pt-BR)")
    p.add_argument("--novel-no-chat", action="store_true", help="ignore Twitch chat")
    p.add_argument("--novel-base-url", default=DEFAULT_BASE_URL,
                   help=f"OpenAI-compatible base URL (default {DEFAULT_BASE_URL})")
    p.add_argument("--novel-model", default=DEFAULT_MODEL,
                   help=f"vision model id (default {DEFAULT_MODEL})")
    p.add_argument("--novel-key", default=None,
                   help="API key (else DEEPSEEK_API_KEY / NOVEL_API_KEY, from the shell or .env)")
    p.add_argument("--novel-describer", choices=DESCRIBERS, default="openai",
                   help="describer backend (scripted/null = offline)")
    p.add_argument("--list-sinks", action="store_true")
    return p


def sink_kwargs(args: argparse.Namespace, source: Source) -> dict:
    """Map the CLI arguments onto the novel sink's constructor."""
    return {
        "interval": args.novel_interval,
        "change_threshold": args.novel_change_threshold,
        "style": args.novel_style,
        "lang": args.novel_lang,
        "no_chat": args.novel_no_chat,
        "chat_channel": None if args.novel_no_chat else chat_channel(source),
        "out_path": args.out,
        "base_url": args.novel_base_url,
        "model": args.novel_model,
        "api_key": args.novel_key,
        "describer": args.novel_describer,
        "label": source.name,
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # a .env here (or at the repo root) supplies DEEPSEEK_API_KEY / NOVEL_API_KEY
    args = build_parser().parse_args(argv)

    if args.list_sinks:
        from streamkit.sink import registered_sinks

        print("\n".join(registered_sinks()))
        return 0

    return run_pipeline_from_args(
        args,
        sink_name=args.sink,
        sink_kwargs=lambda source: sink_kwargs(args, source),
        prog="stream-in-novel",
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
