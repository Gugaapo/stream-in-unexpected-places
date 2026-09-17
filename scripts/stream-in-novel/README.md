# stream-in-novel

A live Twitch stream played into a medium it was never meant for: **prose**. Every 15 seconds a
vision model looks at a still frame, reads the chat, and writes the next two to four sentences of a
story that is happening right now. The text streams into your terminal as it is written, and the whole
run is saved as a novel you can read afterwards.

Part of [**stream in unexpected places**](../..) — one repository, one script per medium. This is the
prose medium. Its sibling [`../stream-in-terminal`](../stream-in-terminal) plays the same stream as
terminal pixel art.

A stream becomes slow television you *read*. The register is a flag: a literary novel, a nature
documentary observing a human at a keyboard, or hard-boiled noir.

## Install

Run every command from this directory (`scripts/stream-in-novel`):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e .          # Windows
# source .venv/bin/activate && pip install -e .   # Linux / WSL
.venv/Scripts/python -m pip install streamlink    # or yt-dlp, for Twitch sources
```

Runtime dependency: **numpy only** (the HTTP client, the PNG encoder and the Twitch IRC client are all
stdlib). `streamlink` (preferred) or `yt-dlp` is needed for Twitch sources, and `ffmpeg` for
everything except `pattern:` sources. The test suite needs neither.

## Usage

```bash
# Offline: no key, no network, no ffmpeg — scripted paragraphs, so the loop is inspectable
PYTHONPATH=src .venv/Scripts/python -m streamkit --source pattern:noise --size 640x360 --fps 2 \
    --sink novel_txt --novel-interval 1 --novel-change-threshold 0 --novel-describer scripted \
    --novel-no-chat --out out/novel/evidence.md --seconds 10 --pace realtime

# Live Twitch -> ANSI novel in the terminal
PYTHONPATH=src .venv/Scripts/python -m streamkit --source twitch:oMeiaUm --size 640x360 --fps 2 \
    --sink novel --novel-interval 15 --novel-style novel --novel-lang pt-BR \
    --out out/novel/omeiaum.md --seconds 180

# Same run as plain text on stdout (no escapes)
PYTHONPATH=src .venv/Scripts/python -m streamkit --source twitch:oMeiaUm --size 640x360 --fps 2 \
    --sink novel_txt --novel-style noir --out out/novel/omeiaum.md

PYTHONPATH=src .venv/Scripts/python -m streamkit --list-sinks
```

After `pip install -e .` the `streamkit` console script is also on PATH, so the `PYTHONPATH=src`
prefix is optional.

Source specs:

| Spec | Meaning |
|------|---------|
| `pattern:bars\|square\|sweep\|noise` | deterministic synthetic video — no ffmpeg, no network (the test harness) |
| `file:/path/video.mp4` | local file through ffmpeg |
| `url:https://...m3u8` | any direct media/HLS URL |
| `twitch:oMeiaUm` / bare channel / `https://twitch.tv/oMeiaUm` | resolved with streamlink, then yt-dlp |

Reported on exit: `streamkit: 120 frames in 60.97s (2.0 fps) via novel_txt -> out/novel/omeiaum-live.md`.
Ctrl+C stops cleanly and finalises the sink (the transcript file is closed and the terminal restored).

### The novel sink

Every `--novel-interval` seconds the sink snapshots the current frame plus the recent Twitch chat,
asks a vision model for the next 2–4 sentences of a continuing story, streams the prose into the
terminal (ANSI) or a plain file, and appends a readable markdown transcript under `--out`
(default `out/novel/<channel>-<date>.md`).

Three design rules make it survivable at 15-second beats:

- **`write(frame)` never blocks.** All model calls happen on a single background worker thread. If a
  request is still in flight when the next beat is due, the beat is *skipped*, not queued — a late
  description of an old frame is worthless.
- **Change gate.** A frame that is nearly identical to the last described one is not sent
  (`mean_abs_error` below `--novel-change-threshold`) unless chat produced new lines. A static title
  card must not generate forty paragraphs of filler. This is the single biggest cost lever.
- **Chat is dialogue, not a ticker.** Chat users are characters: their lines are quoted, by name,
  inside the prose. `--novel-no-chat` disables it.

**Capture resolution.** The `ansi`/`ppm_seq` sinks want a small grid (~160×48). A vision model cannot
narrate that — it is a colour blot. Run the novel at `--size 640x360 --fps 2`; that is a per-sink
consideration, not a change to the core's grid contract.

| Flag | Default | Meaning |
|------|---------|---------|
| `--novel-interval` | `15` | Seconds between model calls; skips (does not queue) if a call is in flight |
| `--novel-change-threshold` | `1.5` | Skip near-identical frames (`mean_abs_error`) unless chat advanced |
| `--novel-style` | `dumb` | `dumb` (snarky + precise) / `novel` / `nature` / `noir` |
| `--novel-lang` | `pt-BR` | `pt-BR` / `en` / `auto` (chat-dominant, else Portuguese) |
| `--novel-no-chat` | off | Disable Twitch chat as dialogue |
| `--novel-base-url` | DeepSeek | `https://api.deepseek.com` |
| `--novel-model` | `deepseek-v4-flash-vision-exp` | Any OpenAI-compatible vision model id |
| `--novel-key` | env / `.env` | Else `$DEEPSEEK_API_KEY` → `$NOVEL_API_KEY` (`.env` loaded automatically) |
| `--novel-describer` | `openai` | `openai` / `scripted` / `null` (offline / no-key) |

Put the key in a `.env` file in this directory (gitignored) — see `.env.example`:

```
DEEPSEEK_API_KEY=your-key-here
```

Resolution order: `--novel-key` → process env → `.env` file. Shell env wins over `.env`. With no key
at all the sink still runs: it degrades to the `null` describer, and the live view shows the chat pane
and a "no describer" notice instead of prose.

The same OpenAI-compatible path works against a local server with no code change:

```bash
PYTHONPATH=src .venv/Scripts/python -m streamkit --source twitch:oMeiaUm --size 640x360 --sink novel \
    --novel-base-url http://127.0.0.1:11434/v1 --novel-model qwen3-vl:8b
```

Cost, measured on DeepSeek V4-Flash (2026-09-16): ~384 tokens per 640×360 image + ~700 tokens of
prompt/context in, ~120 out. At one call per 15 s that is ≈ **$0.08/h** off-peak on published rates —
re-measure on your own account.

## Layout

```
src/streamkit/
  grid.py                 Grid + resamplers (area = integral/box weights, nearest = legacy)
  sink.py                 Sink protocol + registry (register/build_sink/registered_sinks)
  cli.py, __main__.py     the CLI
  ffmpeg.py               find_ffmpeg(): FFMPEG_PATH -> PATH -> WinGet install dir
  sources/
    pattern.py            bars / square / sweep / noise, deterministic, no ffmpeg
    live.py               TwitchSource, FileSource, UrlSource (Grid adapters over the pipe)
    twitch.py             PORT of stream-in-terminal's stream.py (sha256-identical)
    ffmpeg_source.py      PORT of stream-in-terminal's ffmpeg_pipe.py (one documented fix, below)
  describe.py             Describer seam: OpenAI-compat (stdlib urllib + SSE) / scripted / null
  novel.py                Pure story state + prompts + change gate (no I/O)
  render/
    terminal.py           PORT of stream-in-terminal's render.py (sha256-identical)
    png.py                Stdlib RGB8 PNG encoder — what the model actually sees (no Pillow)
  chat.py                 Twitch IRC chat — anonymous justinfan, ported helpers
  sinks/
    novel.py              novel (ANSI) / novel_txt (plain) — the medium
    ansi.py               terminal pixel art (the core's reference sink)
    ppm_seq.py            one PPM per frame — the debug/verification sink
tests/                    unittest suite (also green under pytest)
docs/plan-novel.md        the build brief for this medium, kept as a record
.env.example              the key the sink looks for
```

Ported files are verbatim copies and must not be edited (their hashes are the fidelity contract; the
regression test in `tests/test_ansi_regression.py` re-renders frames through both copies and compares
the bytes). The single deviation:

> `sources/ffmpeg_source.py` — `-headers` is now only passed for `http(s)` inputs. ffmpeg 8.x aborts
> with `Option headers not found` for local files, which made `file:` sources unusable. The sibling
> copy still has the unconditional form; do not sync this back blindly.

## Writing another sink

A sink is three methods. Register it and it is immediately usable from the CLI:

```python
from streamkit.grid import Grid
from streamkit.sink import register

@register("my_medium")
class MySink:
    def __init__(self, *, out_dir: str = "out") -> None:
        self.out_dir = out_dir
        self.frames_written = 0

    def open(self, width: int, height: int) -> None:   # called once, dimensions are fixed here
        self.size = (width, height)

    def write(self, grid: Grid) -> None:               # grid.rgb is uint8 (h, w, 3)
        grid.resize(320, 240, method="area").save_ppm(f"{self.out_dir}/f{grid.index:05d}.ppm")
        self.frames_written += 1

    def close(self) -> None:                           # must be idempotent; also runs on error
        pass
```

`Grid` helpers: `.rgb` (numpy array), `.rgb_bytes` (RGB24 bytes), `.resize(w, h, method="area"|"nearest")`,
`.save_ppm(path)`, `.mean_abs_error(other)`, `.index`, `.t`, `.meta`. New sinks must be imported from
`src/streamkit/sinks/__init__.py` or they never register.

**`method="nearest"` reproduces the historical stream-in-terminal sampler exactly** (needed for
terminal fidelity); `method="area"` is a box-area average and is the right default for video.

## Verified

**Test suite — this repo, Windows host 2026-09-17** (Python 3.11.8, this script's venv, numpy 2.4.6,
streamlink 8.6.1, ffmpeg 8.0.1):

```
$ PYTHONPATH=src .venv/Scripts/python -m unittest discover -s tests -t tests
Ran 50 tests in 5.149s

OK
```

Everything except one file-source test runs with no ffmpeg, no network and no API key — the
`pattern:` sources and the `scripted` describer exist for exactly that.

**Offline end-to-end (scripted describer), 2026-09-17:**

```
$ PYTHONPATH=src .venv/Scripts/python -m streamkit --source pattern:noise --size 640x360 --fps 2 \
      --sink novel_txt --novel-interval 1 --novel-change-threshold 0 --novel-describer scripted \
      --novel-no-chat --out out/novel/evidence-scripted.md --seconds 10 --pace realtime
streamkit: 20 frames in 9.56s (2.1 fps) via novel_txt -> out\novel\evidence-scripted.md
```

```
# novel - pattern:noise
style: dumb | lang: pt-BR | started: 2026-09-17T11:39:52

Bars of colour marched across the void like a parade with nowhere to go.
Someone in chat whispered a name, and the parade hesitated - then marched on.
...
```

9 paragraphs appended in order.

**Live Twitch with real model calls — this repo, 2026-09-17 11:36 -04:00, channel `oMeiaUm`:**

```
$ PYTHONPATH=src .venv/Scripts/python -m streamkit --source twitch:oMeiaUm --size 640x360 --fps 2 \
      --sink novel_txt --novel-interval 15 --novel-style dumb --novel-lang pt-BR \
      --out out/novel/omeiaum-live.md --seconds 60
streamkit: 120 frames in 60.97s (2.0 fps) via novel_txt -> out\novel\omeiaum-live.md
```

Four beats in 60 s produced this (transcript excerpt, Brazilian Portuguese, chat quoted by name —
those are real chat users of that run):

> "O cronômetro marca 403:28:13 e o bonequinho de armadura continua plantado na frente da mesma porta
> enferrujada, esperando talvez que ela abra por educação. O chat tenta ajudar de verdade, com
> FogueiraDoNoite pedindo as sentenças e Fujurildo avisando que se tocar a música do dragão o cara
> fica cego — dica que claramente ninguém ali vai seguir."

The model read the on-screen countdown, the game scene and the overlay text off a 640×360 still, then
wove eight chat lines into the story by name — not a description of a colour blot. An earlier gate on
the same host (2026-09-16, recorded in `docs/plan-novel.md`) checked that three stills from one live
connection, spaced by real wall-clock time, were all narratable.

Honest limit: the prose is only as good as a 640×360 still every 15 s plus eight chat lines. Silence
in chat and a static scene produce a stalled story — that is the change gate working, not a bug.

## Environment gotchas (cost real time)

- **WSL may have no ffmpeg, no Pillow, no streamlink and no pytest.** Hence: tests are `unittest`-style
  (they run under both `pytest` and `unittest discover`), the synthetic `pattern:` sources need no
  ffmpeg, and debug frames are PPM (stdlib) rather than PNG. Live runs happen on a host that has
  ffmpeg + streamlink and a normal terminal.
- **`build_sink(sink_name, **options)`** — the first parameter is not called `name`, because sinks
  take their own `name` option (default output filename).
- **ffmpeg 8.x rejects `-headers` for non-HTTP inputs** (see the deviation note above).
- **DeepSeek V4 defaults to thinking**: with a small `max_tokens` budget the whole reply lands in
  `reasoning_content` and the visible content is empty, so the request sends
  `thinking: {type: disabled}`. `reasoning_content` deltas are ignored on the way back.
- **HTTP 429 needs a long cool-down.** The sink backs off 60 s on a rate-limit instead of retrying
  every 15 s and burning quota; other transport errors just pause the story.
- Realtime pacing is the CLI default; `--pace fast` is for tests, where a run's file duration comes
  from metadata (`frames / fps`) rather than wall time.
- If a Twitch channel is offline you get a one-line `error: Stream offline or not found ...` and exit
  code 2 — not a stack trace.

## License

MIT — see the repository's [LICENSE](../../LICENSE).
