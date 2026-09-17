# stream-in-terminal

Watch a **live Twitch stream** as coloured pixel art in your terminal — the half-block /
background-colour technique used by
[pokemon-terminal-art](https://github.com/shinya/pokemon-terminal-art), with live chat underneath.

Part of [**stream in unexpected places**](../..) — one repository, one medium per script. This is the
terminal medium, and it is the one medium here that is an *app* rather than a plain sink: a player
loop, a chat pane, alt-screen handling, and `--record` to save what you see as an MP4.

It is built on [`streamkit`](../../), the library at this repository's root. Everything upstream of
the drawing — Twitch resolution, the ffmpeg decode pipe, the Grid, the terminal renderer, the chat
client, the ffmpeg lookup — is the library's; what lives here is the player itself.
(It was previously published on its own as `live-in-terminal`.)

## Showcase

[oMeiaUm](https://www.twitch.tv/oMeiaUm), recorded with this script's `--record` flag:

[![oMeiaUm in the terminal](./showcase_omeiaum.mp4)](./showcase_omeiaum.mp4)

The recorded clip is 960×432 @ 8 fps — pixel art, the status line and the chat rows, encoded by
ffmpeg with no screen-capture software.

## How it works

```
streamlink / yt-dlp  ->  HLS URL  ->  ffmpeg (raw RGB24)  ->  Grid  ->  resample + ANSI  ->  terminal
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  the streamkit library
```

1. **streamlink** (preferred) or **yt-dlp** resolves `twitch.tv/<channel>` to an HLS URL
   (`streamkit.sources.TwitchSource`).
2. **ffmpeg** decodes frames to raw RGB at a fixed decode grid (`--decode`, default `160x48`) and the
   library wraps each frame in a `Grid`.
3. The player resamples each frame to the live terminal size and the library renders it: **256-colour
   ANSI** (default) or **24-bit truecolor** (`--color`).
4. **compact** mode draws two pixel rows per terminal row with `▀` (the default); **blocks** mode
   draws two coloured spaces per pixel; **ascii** mode is the legacy character ramp.
5. Chat is read over anonymous Twitch IRC (`justinfan`, no login, no OAuth) and printed under the
   status line.

Latency is a few seconds (HLS). Aim for ~8–15 fps depending on terminal size and CPU.

## Requirements

| Dependency | Role |
|------------|------|
| Python 3.10+ | the player |
| [ffmpeg](https://ffmpeg.org/) | decode video, encode `--record` MP4s |
| [streamlink](https://streamlink.github.io/) **or** [yt-dlp](https://github.com/yt-dlp/yt-dlp) | resolve the Twitch live URL |

No Twitch API key is required for public live streams.

**Install helpers**

Linux (Debian/Ubuntu example):

```bash
sudo apt update
sudo apt install -y python3 ffmpeg
pipx install streamlink          # or: pip install --user streamlink
```

Windows:

```powershell
winget install Gyan.FFmpeg
pip install streamlink           # or: pip install yt-dlp
```

Use [Windows Terminal](https://aka.ms/terminal) for reliable ANSI / 256-colour output.

## Install

The library is installed from this repository's root (never from PyPI — that name belongs to an
unrelated project), then this medium. Run every command from this directory
(`scripts/stream-in-terminal`):

```bash
python -m venv .venv

# Windows
.venv/Scripts/python -m pip install -e ../..        # 1. streamkit
.venv/Scripts/python -m pip install -e .            # 2. this medium
.venv/Scripts/python -m pip install streamlink

# Linux / macOS / WSL
source .venv/bin/activate
pip install -e ../..
pip install -e .
pip install streamlink
```

You can skip `pip install -e .` and use the launchers — `watch.sh` / `watch.ps1` set
`PYTHONPATH=src` when the package is not installed, and they check Python, ffmpeg and
streamlink/yt-dlp before starting. The library (`pip install -e ../..`) is still needed: the launchers
cannot supply that. If it is missing, the entry point prints one line telling you the exact command to
run instead of a traceback.

## Usage

**Linux / macOS / WSL:**

```bash
chmod +x watch.sh
./watch.sh oMeiaUm
./watch.sh oMeiaUm --fps 12 --quality 480p
./watch.sh oMeiaUm --mode blocks --color
./watch.sh oMeiaUm --mode ascii --no-color
./watch.sh oMeiaUm --quality 720p --fps 15 --decode 240x72
./watch.sh oMeiaUm --record showcase_omeiaum.mp4
./watch.sh https://www.twitch.tv/oMeiaUm --no-chat
```

**Windows (PowerShell):**

```powershell
.\watch.ps1 oMeiaUm
.\watch.ps1 oMeiaUm --fps 10 --mode compact
.\watch.ps1 oMeiaUm --quality 720p
.\watch.ps1 oMeiaUm --chat-lines 8
```

**Directly (module or console script, after `pip install -e .`):**

```bash
python -m stream_in_terminal oMeiaUm --fps 12
stream-in-terminal oMeiaUm --fps 12
sit oMeiaUm --fps 12
```

Any of these work with a channel name (`oMeiaUm`), a URL (`https://www.twitch.tv/oMeiaUm`) or a
`--decode` grid tuned to your screen. Exit with **Ctrl+C**; if the channel is offline you get a clear
one-line error instead of a stack trace.

### Options

| Flag | Description |
|------|-------------|
| `--fps N` | Target FPS (default `12`, capped 1–30) |
| `--width N` | Terminal width in characters (default: the real terminal width) |
| `--mode` | `compact` (half-block `▀`, default), `blocks` (coloured spaces), or `ascii` (legacy) |
| `--decode WxH` | ffmpeg decode grid before the terminal resample (default `160x48`; try `240x72` or `320x90` for fullscreen) |
| `--quality` | `best`, `worst`, `1080p`, `720p`, `480p`, `360p`, `160p` |
| `--chars` | Charset for `--mode ascii`: `classic`, `blocks`, or a custom dark-to-bright ramp |
| `--no-color` | Grayscale block density (no ANSI colours) |
| `--color` | 24-bit truecolor instead of the 256-colour palette |
| `--no-chat` | Hide Twitch chat under the video |
| `--chat-lines N` | Chat rows under the video (default `5`) |
| `--record [PATH]` | Record pixel art + status + chat to an MP4 via ffmpeg (default: `<channel>_<timestamp>.mp4`) |
| `--record-scale N` | Pixels per art pixel in the recording (default `8`) |
| `--version` | Print the version |

## Render modes

| Mode | Technique | Looks like |
|------|-----------|------------|
| **compact** (default) | `▀` half-blocks, fg/bg ANSI colours | [pokemon-terminal-art compact](https://github.com/shinya/pokemon-terminal-art) |
| **blocks** | Two coloured spaces per pixel | [pokemon-terminal-art normal](https://github.com/shinya/pokemon-terminal-art) |
| **ascii** | Character density ramp | the original live-in-terminal look |

## Chat

Live chat is on by default: the last **5** messages appear under the status line, read over anonymous
Twitch IRC. `--no-chat` turns it off; `--chat-lines 8` shows more. Usernames are coloured from the
colour Twitch sends (fallback hues when it sends none), using `streamkit.chat` — the same client the
novel medium narrates from.

## Recording

`--record` saves exactly what you see — pixel art, status line and chat — to an MP4 without OBS. The
overlay is drawn with an embedded 8×8 VGA font and a stdlib PNG/zlib path, so there is no Pillow or
screen-capture dependency. Recording dimensions are locked when the session starts.

```bash
./watch.sh oMeiaUm --record
./watch.sh oMeiaUm --record my_clip.mp4 --record-scale 12
```

## Verified

**This repo, Windows host, 2026-09-17 (Python 3.11.8, ffmpeg 8.0.1, streamlink 8.6.1), channel
`oMeiaUm`, live, after the medium was switched to the library:**

```
$ .venv/Scripts/python -m stream_in_terminal oMeiaUm --fps 8 --quality 480p --chat-lines 5 \
      --record out/omeiaum-live.mp4
115 frames rendered; log tail (ANSI stripped):
omeiaum | compact 120x48 @ 8fps | Ctrl+C quit
Aniyn_: orlaine
OOOOOOOVER: qual plataforma
toddyn_liruliru: open bar da Subathon? Bebo
```

```
$ ffprobe -v error -select_streams v:0 \
      -show_entries stream=codec_name,width,height,nb_frames,r_frame_rate \
      -of default=noprint_wrappers=1 out/omeiaum-live.mp4
codec_name=h264
width=960
height=432
r_frame_rate=8/1
nb_frames=114
duration=14.250000
size=927091
```

The recording was made with `--record`; the player was then interrupted (Windows `CTRL_BREAK`, the
nearest scripted equivalent of Ctrl+C in a console) and the MP4 was still complete and readable —
114 frames, `duration=14.250000`. A real Ctrl+C in a terminal runs the same clean shutdown path.

The renderer this medium draws with is the library's (`streamkit.render.terminal`), and its exact
output is pinned by hash in the library's `tests/test_render_golden.py` — the bytes are the ones the
original live-in-terminal produced, so a refactor cannot silently change what you see.

## Layout

```
src/stream_in_terminal/
  cli.py, __main__.py   the CLI (player flags, --record) and the entry point
  player.py             the player loop: layout, status line, chat pane, pacing, recording
  record.py             the MP4 recorder (ffmpeg pipe)
  record_overlay.py     renders the recorded frame: pixel art + status + chat, embedded VGA font
```

Everything else comes from the library: sources (`streamkit.sources.TwitchSource`), frames
(`streamkit.grid.Grid`), the renderer (`streamkit.render.terminal`), chat (`streamkit.chat`), the
ffmpeg lookup (`streamkit.ffmpeg`). Building a medium of your own? Start at
[`docs/writing-a-medium.md`](../../docs/writing-a-medium.md).

## Notes and gotchas

- Video only — no audio.
- Legacy Windows `conhost` may show poor colours; use Windows Terminal.
- Lower `--quality` / `--fps` / `--decode` if the terminal cannot keep up.
- Resizing the window is supported: frames are decoded at the fixed `--decode` grid and resampled to
  the live terminal size, with no stream restart. While `--record` is active the layout stays locked so
  the MP4 stays stable.
- For a sharper fullscreen picture raise `--decode` (e.g. `240x72`) and `--quality 720p`; both cost CPU.
- The renderer is shared with every other medium in this repository. If you change how a frame is
  drawn, you are changing it for all of them — and `tests/test_render_golden.py` in the library will
  tell you, loudly, which bytes moved.

## License

MIT — see the repository's [LICENSE](../../LICENSE).
