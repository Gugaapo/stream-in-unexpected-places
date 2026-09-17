# stream-in-novel

A live Twitch stream played into a medium it was never meant for: **prose**. Every 15 seconds a
vision model looks at a still frame, reads the chat, and writes the next two to four sentences of a
story that is happening right now. The text streams into your terminal as it is written, and the whole
run is saved as a novel you can read afterwards.

This is a **medium built on [`streamkit`](../../)**, the library at this repository's root. What lives
here is the medium: the prose sink, the story/prompt logic and its CLI. Everything upstream — Twitch
resolution, the ffmpeg decode pipe, the Grid, the chat client, the vision-model seam, the PNG encoder,
the run loop — is the library's. Its sibling [`../stream-in-terminal`](../stream-in-terminal) plays
the same stream as terminal pixel art.

A stream becomes slow television you *read*. The register is a flag: a literary novel, a nature
documentary observing a human at a keyboard, or hard-boiled noir.

## Install

The library is installed from this repository's root (never from PyPI — that name belongs to an
unrelated project), then this medium:

```bash
cd scripts/stream-in-novel
python -m venv .venv
.venv/Scripts/python -m pip install -e ../..        # 1. streamkit
.venv/Scripts/python -m pip install -e .            # 2. this medium
.venv/Scripts/python -m pip install streamlink      # or yt-dlp, for Twitch sources
```

On Linux / macOS / WSL, activate the venv instead of prefixing `.venv/Scripts/python`. Runtime
dependency: **numpy only** — the HTTP client, the PNG encoder and the IRC client are stdlib and come
with the library. `ffmpeg` is needed for everything except `pattern:` sources; the tests need neither.

## Usage

The console script is `stream-in-novel` (equivalently `python -m stream_in_novel`):

```bash
# Offline: no key, no network, no ffmpeg — scripted paragraphs, so the loop is inspectable
.venv/Scripts/stream-in-novel --source pattern:noise --size 640x360 --fps 2 --sink novel_txt \
    --novel-interval 1 --novel-change-threshold 0 --novel-describer scripted --novel-no-chat \
    --out out/novel/evidence.md --seconds 10 --pace realtime

# Live Twitch -> ANSI novel in the terminal
.venv/Scripts/stream-in-novel --source twitch:oMeiaUm --size 640x360 --fps 2 --sink novel \
    --novel-interval 15 --novel-style novel --novel-lang pt-BR \
    --out out/novel/omeiaum.md --seconds 180

# Same run as plain text (no escapes) — pipe-friendly
.venv/Scripts/stream-in-novel --source twitch:oMeiaUm --size 640x360 --fps 2 --sink novel_txt \
    --novel-style noir --out out/novel/omeiaum.md

# A local file instead of a live stream
.venv/Scripts/stream-in-novel --source file:clip.mp4 --size 640x360 --fps 2 --sink novel
```

Source specs (the same in every medium, because they come from the library):

| Spec | Meaning |
|------|---------|
| `pattern:bars\|square\|sweep\|noise` | deterministic synthetic video — no ffmpeg, no network (the test harness) |
| `file:/path/video.mp4` | local file through ffmpeg |
| `url:https://...m3u8` | any direct media/HLS URL |
| `twitch:oMeiaUm` / bare channel / `https://twitch.tv/oMeiaUm` | resolved with streamlink, then yt-dlp |

Reported on exit: `stream-in-novel: 120 frames in 61.06s (2.0 fps) via novel_txt -> out/novel/omeiaum-live.md`.
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
  inside the prose, and the channel owner is tagged as the streamer rather than as a viewer.
  `--novel-no-chat` disables it.

**Capture resolution.** The terminal medium plays at ~160×48. A vision model cannot narrate that — it
is a colour blot — so this medium runs at `--size 640x360 --fps 2`. That is a per-medium decision, not
a library change.

### Novel flags

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

The rest of the flags (`--source`, `--size`, `--fps`, `--quality`, `--out`, `--seconds`, `--frames`,
`--pace`, `--quiet`) come from the library's `add_core_arguments` and are identical in every medium.

Put the key in a `.env` file in this directory (gitignored) — see `.env.example`:

```
DEEPSEEK_API_KEY=your-key-here
```

Resolution order: `--novel-key` → process env → `.env` (a `.env` in this directory, or at the
repository root). Shell env wins over `.env`, and `--novel-key ""` deliberately means "no key". With
no key at all the sink still runs: it degrades to the `null` describer, and the live view shows the
chat pane and a "no describer" notice instead of prose.

The same OpenAI-compatible path works against a local server with no code change:

```bash
.venv/Scripts/stream-in-novel --source twitch:oMeiaUm --size 640x360 --sink novel \
    --novel-base-url http://127.0.0.1:11434/v1 --novel-model qwen3-vl:8b
```

Cost, measured on DeepSeek V4-Flash (2026-09-16): ~384 tokens per 640×360 image + ~700 tokens of
prompt/context in, ~120 out. At one call per 15 s that is ≈ **$0.08/h** off-peak on published rates —
re-measure on your own account.

## Layout

```
src/stream_in_novel/
  novel.py              the story: state, style/language prompts, the change gate (pure, no I/O)
  sinks/novel.py        the medium: novel (ANSI live view) / novel_txt (plain text)
  cli.py, __main__.py   this medium's CLI (core flags + --novel-*), and the entry point
tests/                  10 offline tests: prompt assembly, the gate, non-blocking writes, transcript
docs/plan-novel.md      the original build brief for this medium, kept as a record
.env.example            the key the describer seam looks for
```

Everything else is the library: `streamkit.sources` (sources), `streamkit.grid` (frames),
`streamkit.chat` (Twitch IRC), `streamkit.describe` (the vision-model seam), `streamkit.render.png`
(the still the model sees), `streamkit.pipeline` (the run loop), `streamkit.cli` (the shared flags).

Building a medium of your own? Start at [`docs/writing-a-medium.md`](../../docs/writing-a-medium.md).

## Verified

**Test suite — this repo, Windows host 2026-09-17** (Python 3.11.8, this medium's venv, numpy 2.4.6,
streamlink 8.6.1, ffmpeg 8.0.1):

```
$ .venv/Scripts/python -m unittest discover -s tests -t tests
Ran 10 tests in 2.482s

OK
```

Plus the library's own 53 tests, which cover the shared pieces this medium stands on.

**Offline end-to-end (scripted describer), 2026-09-17:**

```
$ .venv/Scripts/stream-in-novel --source pattern:noise --size 640x360 --fps 2 --sink novel_txt \
      --novel-interval 1 --novel-change-threshold 0 --novel-describer scripted --novel-no-chat \
      --out out/novel/evidence-scripted.md --seconds 10 --pace realtime
stream-in-novel: 20 frames in 9.50s (2.1 fps) via novel_txt -> out\novel\evidence-scripted.md
```

```
# novel - pattern:noise
style: dumb | lang: pt-BR | started: 2026-09-17T11:58:02

Bars of colour marched across the void like a parade with nowhere to go.
Someone in chat whispered a name, and the parade hesitated - then marched on.
...
```

9 paragraphs appended in order.

**Live Twitch with real model calls — this repo, 2026-09-17 11:58 -04:00, channel `oMeiaUm`:**

```
$ .venv/Scripts/stream-in-novel --source twitch:oMeiaUm --size 640x360 --fps 2 --sink novel_txt \
      --novel-style dumb --novel-lang pt-BR --out out/novel/omeiaum-live.md --seconds 60
stream-in-novel: 120 frames in 61.06s (2.0 fps) via novel_txt -> out\novel\omeiaum-live.md
```

Four beats in 61 s produced four paragraphs; this is the first one (Brazilian Portuguese, chat quoted
by name — those are real chat users from that run):

> "O careca de regata branca agora está parado na frente de um carro vermelho, com o letreiro "NO
> SMOKING" ainda atrás dele e o cronômetro batendo 404:27:50. O omeiaum continua sorrindo no cantinho,
> sem escolher nada, enquanto a galera no chat já tá discutindo dublagem e remake em vez de jogar. O
> AntonyTLK1 solta um "omg é o cesar", e é basicamente isso: o streamer levou quase quatrocentas horas
> pra encontrar um cara num armário e chamar de decisão."

The model read the on-screen countdown, the scene and the overlay text off a 640×360 still, then wove
the chat into the story by name — not a description of a colour blot. An earlier gate on the same host
(2026-09-16, recorded in `docs/plan-novel.md`) checked that three stills from one live connection,
spaced by real wall-clock time, were all narratable.

Honest limit: the prose is only as good as a 640×360 still every 15 s plus eight chat lines. Silence
in chat and a static scene produce a stalled story — that is the change gate working, not a bug.

## Environment gotchas (cost real time)

- **Tests must never touch the network or the ambient environment.** `pattern:` sources plus the
  `scripted` describer; the library's key-resolution tests patch the environment precisely because a
  developer machine really does have `DEEPSEEK_API_KEY` exported.
- **`build_sink(sink_name, **options)`** — the first parameter is not called `name`, because sinks
  take their own `name`/`label` option (default output filenames).
- **ffmpeg 8.x rejects `-headers` for non-HTTP inputs.** The library's `sources/ffmpeg_source.py`
  handles it (it only sends `-headers` for `http(s)`); a `file:` source therefore works.
- **DeepSeek V4 defaults to thinking**: with a small `max_tokens` budget the whole reply lands in
  `reasoning_content` and the visible content is empty, so the request sends
  `thinking: {type: disabled}`. `reasoning_content` deltas are ignored on the way back.
- **HTTP 429 needs a long cool-down.** The sink backs off 60 s on a rate-limit instead of retrying
  every 15 s and burning quota; other transport errors just pause the story.
- Realtime pacing is the default; `--pace fast` is for tests, where a run's file duration comes from
  metadata (`frames / fps`) rather than wall time.
- If a Twitch channel is offline you get a one-line `error: Stream offline or not found ...` and exit
  code 2 — not a stack trace.

## License

MIT — see the repository's [LICENSE](../../LICENSE).
