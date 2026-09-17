# stream in unexpected places

Play a **live Twitch stream** into a medium it was never meant for. One repository, one script per
medium — each script self-contained, installable and runnable on its own.

Every example in this repository uses the [**oMeiaUm**](https://www.twitch.tv/oMeiaUm) channel.

## Scripts

| Script | The medium | Needs (beyond Python 3.10+) |
|--------|-----------|------------------------------|
| [`scripts/stream-in-terminal`](scripts/stream-in-terminal/) | **Terminal pixel art.** The stream renders as coloured half-blocks with the chat underneath, live in your terminal. | `ffmpeg`, `streamlink` (or `yt-dlp`) |
| [`scripts/stream-in-novel`](scripts/stream-in-novel/) | **Language.** A vision model reads a still frame every 15 s, reads the chat, and writes the stream as prose — live in your terminal, saved as a novel. | `ffmpeg`, `streamlink`, one vision-model API key |

Each script directory contains the script itself and its own README, which explains that medium in
depth: how it works, install, every flag, real examples, what was verified, and the honest limits.

## Quick start

```bash
git clone https://github.com/Gugaapo/stream-in-unexpected-places.git
cd stream-in-unexpected-places
```

**The stream as terminal pixel art**

```bash
cd scripts/stream-in-terminal
python -m venv .venv
.venv/Scripts/python -m pip install -e .          # Windows
# source .venv/bin/activate && pip install -e .   # Linux / macOS / WSL
.venv/Scripts/python -m pip install streamlink

./watch.sh oMeiaUm                                 # Windows: .\watch.ps1 oMeiaUm
```

**The stream as a novel**

```bash
cd scripts/stream-in-novel
python -m venv .venv
.venv/Scripts/python -m pip install -e .
.venv/Scripts/python -m pip install streamlink
echo "DEEPSEEK_API_KEY=your-key-here" > .env       # .env is gitignored

PYTHONPATH=src .venv/Scripts/python -m streamkit --source twitch:oMeiaUm --size 640x360 --fps 2 \
    --sink novel --novel-style novel --novel-lang pt-BR --out out/novel/omeiaum.md
```

## Layout

```
scripts/
  stream-in-terminal/          the terminal medium
    README.md                  the script readme — how it works, install, flags, examples, limits
    pyproject.toml             its own installable project
    src/stream_in_terminal/    player, renderer, chat, MP4 recorder
    watch.sh, watch.ps1        one-command launchers (they check ffmpeg / streamlink for you)
    showcase_omeiaum.mp4       a real capture, made with this script

  stream-in-novel/             the prose medium
    README.md                  the script readme
    pyproject.toml             its own installable project
    src/streamkit/             source -> Grid -> sink core, plus the novel sink
    tests/                     50-test unittest suite, runs offline (no ffmpeg, no network, no key)
    docs/plan-novel.md         the original build brief, kept as a build record
    .env.example               the API key the sink looks for

LICENSE                        MIT
```

## Conventions (for the next script)

1. **One directory per medium:** `scripts/<script-name>/`.
2. **Self-contained.** Its own `pyproject.toml`, installable with `pip install -e .`. No shared
   package to import from a sibling.
3. **Ship a script readme** (`README.md` inside the script directory): what the medium is, how it
   works, install steps, a table of every flag, several real examples, the verification evidence,
   and the honest limits.
4. **Examples use the `oMeiaUm` channel.**
5. **Output goes to `out/` and secrets go to `.env`** — both gitignored, at every level.
6. **Ported code is copied, not linked.** If a script ports code from a sibling, the ported file is a
   byte-identical copy and a regression test proves it: see
   `scripts/stream-in-novel/tests/test_ansi_regression.py`, which renders the same frames with its own
   terminal renderer and with `stream-in-terminal`'s, and asserts the bytes match.

## Verified

Both scripts were exercised live against `oMeiaUm` on 2026-09-17 (Windows host, Python 3.11.8,
ffmpeg 8.0.1, streamlink 8.6.1) — see each script's README for the full output:

| Script | Evidence |
|--------|----------|
| `stream-in-terminal` | 113 frames rendered live at 8 fps (status line + real chat rows), and an h264 `960x432` / 8 fps / 113-frame MP4 recorded with `--record` |
| `stream-in-novel` | 2.0 fps capture for 60 s → 4 model-written paragraphs in Brazilian Portuguese naming real chat users; plus a `Ran 50 tests … OK` offline suite |

## Requirements

| Dependency | Role | Needed by |
|------------|------|-----------|
| Python 3.10+ | both scripts | all |
| [ffmpeg](https://ffmpeg.org/) | decode the stream, encode recordings | all |
| [streamlink](https://streamlink.github.io/) (or [yt-dlp](https://github.com/yt-dlp/yt-dlp)) | resolve the Twitch live URL | all |
| A vision-model API key (DeepSeek by default) | turn stills into prose | `stream-in-novel` |

No Twitch API key is needed: public live streams are resolved anonymously, and chat is read over
anonymous IRC.

## License

MIT — see [LICENSE](LICENSE).
