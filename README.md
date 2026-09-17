# stream in unexpected places

Play a **live Twitch stream** into a medium it was never meant for.

This repository is two things:

- **`streamkit`** — the library at the root. Sources, frames, a sink registry, a describer seam,
  chat, renderers and the shared run loop. It is what a new medium is built on.
- **`scripts/`** — the mediums built on it, one self-contained project per medium: the code, its own
  README, its own install, its own tests.

Every example in this repository uses the [**oMeiaUm**](https://www.twitch.tv/oMeiaUm) channel.

## The mediums

| Script | The medium | Needs |
|--------|-----------|-------|
| [`scripts/stream-in-terminal`](scripts/stream-in-terminal/) | **Terminal pixel art.** The stream renders as coloured half-blocks with the chat underneath, live. `--record` saves the whole thing to an MP4. | `ffmpeg`, `streamlink` (or `yt-dlp`) |
| [`scripts/stream-in-novel`](scripts/stream-in-novel/) | **Language.** A vision model reads a still frame every 15 s, reads the chat, and writes the stream as prose — live in the terminal, saved as a novel. | `ffmpeg`, `streamlink`, one vision-model API key |

## Quick start

```bash
git clone https://github.com/Gugaapo/stream-in-unexpected-places.git
cd stream-in-unexpected-places
```

Every script installs the library first, then itself, into its own virtualenv:

**The stream as terminal pixel art**

```bash
cd scripts/stream-in-terminal
python -m venv .venv
.venv/Scripts/python -m pip install -e ../..     # 1. the streamkit library
.venv/Scripts/python -m pip install -e .         # 2. this medium
.venv/Scripts/python -m pip install streamlink

./watch.sh oMeiaUm                               # Windows: .\watch.ps1 oMeiaUm
```

**The stream as a novel**

```bash
cd scripts/stream-in-novel
python -m venv .venv
.venv/Scripts/python -m pip install -e ../..     # 1. the streamkit library
.venv/Scripts/python -m pip install -e .         # 2. this medium
.venv/Scripts/python -m pip install streamlink
echo "DEEPSEEK_API_KEY=your-key-here" > .env     # .env is gitignored

.venv/Scripts/stream-in-novel --source twitch:oMeiaUm --size 640x360 --fps 2 \
    --sink novel --novel-style novel --novel-lang pt-BR --out out/novel/omeiaum.md
```

(On Linux / macOS / WSL, activate the venv instead of prefixing `.venv/Scripts/python`.)

## Using the library

```bash
.venv/Scripts/python -m pip install -e .          # from the repository root
.venv/Scripts/streamkit --source twitch:oMeiaUm --size 160x48 --fps 12 --sink ansi
.venv/Scripts/streamkit --source pattern:bars --size 80x24 --sink ppm_seq --out out/frames --seconds 2
.venv/Scripts/streamkit --list-sinks
```

```python
from streamkit.pipeline import run
from streamkit.sink import build_sink
from streamkit.sources import build_source

source = build_source("twitch:oMeiaUm", width=160, height=48, fps=12)   # or file:/url:/pattern:
source.open()
sink = build_sink("ansi", mode="blocks")
sink.open(source.width, source.height)
result = run(source, sink, fps=12, seconds=30)      # pacing, limits, Ctrl+C, closing
print(result.frames, "frames", f"{result.fps:.1f} fps")
```

The library ships two sinks of its own — `ansi` (terminal pixel art) and `ppm_seq` (one PPM per
frame, which is how you eyeball what a medium is receiving) — and a CLI that runs any source into
them. Mediums register their own sinks on top.

**Building a new medium?** Read [`docs/writing-a-medium.md`](docs/writing-a-medium.md): the sink
protocol, the Grid API, the describer seam, the chat client, the CLI helpers, packaging, and the
offline-testing rules, with a complete worked example.

## Layout

```
pyproject.toml                 streamkit, the library
src/streamkit/
  grid.py                      Grid: RGB frames, resamplers, frame-to-frame difference
  sink.py                      the Sink protocol + registry (register / build_sink)
  pipeline.py                  run(source, sink, fps, pace, seconds, frames) -> RunResult
  cli.py                       the CLI + the helpers a medium's CLI reuses
  sources/                     pattern | file | url | twitch -> Grids (ffmpeg, streamlink)
  ffmpeg.py                    find_ffmpeg(): FFMPEG_PATH -> PATH -> WinGet install dir
  chat.py                      anonymous Twitch IRC, chat rows, per-user colours
  describe.py                  the vision-model seam: OpenAI-compatible / scripted / null
  render/terminal.py           the terminal renderer (byte-pinned by tests/test_render_golden.py)
  render/png.py                stdlib RGB8 PNG encoder — the still a vision model sees
  sinks/ansi.py, ppm_seq.py    the reference sinks
tests/                         53-test suite; no ffmpeg, no network, no API key needed
docs/writing-a-medium.md       how to build the next medium

scripts/
  stream-in-terminal/          the terminal medium (player app; uses streamkit)
    src/stream_in_terminal/    player, recorder + chat overlay, CLI
    watch.sh, watch.ps1        one-command launchers (they check ffmpeg / streamlink for you)
    showcase_omeiaum.mp4       a real capture, made with --record
  stream-in-novel/             the prose medium (sink; uses streamkit)
    src/stream_in_novel/       novel.py (story + prompts), sinks/novel.py, CLI
    tests/                     10-test suite, offline
    docs/plan-novel.md         the original build brief, kept as a record
    .env.example               the API key the describer seam looks for

LICENSE                        MIT
```

## Conventions

1. **One directory per medium:** `scripts/<script-name>/`, self-contained (own `pyproject.toml`,
   own venv, own README, own tests).
2. **The library is installed from this repository's root**, never from PyPI — the name `streamkit`
   on PyPI belongs to an unrelated project:
   `python -m pip install -e ../..` then `python -m pip install -e .`
3. **Ship a script README**: what the medium is, how it works, install, a table of every flag, real
   examples, the verification evidence, the honest limits.
4. **Examples use the `oMeiaUm` channel.**
5. **Output goes to `out/`, secrets go to `.env`** — both gitignored at every level.
6. **Tests never touch the network.** Use `pattern:` sources and the `scripted` describer; gate
   anything needing ffmpeg behind a skip.
7. **A medium's sink lives with the medium**, not in the library: the library holds the plumbing.

## Verified

2026-09-17, Windows host (Python 3.11.8, ffmpeg 8.0.1, streamlink 8.6.1), everything run live
against `oMeiaUm`:

| What | Evidence |
|------|----------|
| `streamkit` library | `Ran 53 tests — OK` (no ffmpeg, no network, no key) |
| `stream-in-terminal` | 115 frames rendered live at 8 fps with the chat pane; `--record` produced h264 960x432 @ 8 fps, 114 frames, 14.25 s |
| `stream-in-novel` | `120 frames in 61.06s (2.0 fps)`, 4 model-written paragraphs in Brazilian Portuguese naming real chat users; `Ran 10 tests — OK` |
| The renderer | byte-pinned by hash in `tests/test_render_golden.py` (the output the original live-in-terminal produced) |

## Requirements

| Dependency | Role | Needed by |
|------------|------|-----------|
| Python 3.10+ | the library and every medium | all |
| [ffmpeg](https://ffmpeg.org/) | decode the stream, encode recordings | all |
| [streamlink](https://streamlink.github.io/) (or [yt-dlp](https://github.com/yt-dlp/yt-dlp)) | resolve the Twitch live URL | all |
| numpy | the frames themselves | the library |
| A vision-model API key (DeepSeek by default) | turn stills into prose | `stream-in-novel` |

No Twitch API key is needed: public live streams are resolved anonymously, and chat is read over
anonymous IRC.

## License

MIT — see [LICENSE](LICENSE).
