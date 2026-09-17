# plan-novel.md — Cursor handoff brief (NOVEL: the stream narrates itself as prose, in the terminal)

> Kept as the build record of this medium, written while the shared core still lived in a larger
> scratch monorepo. Everything the novel sink needs is in this repo already.
>
> **Where those files live now (2026-09-17, after the library split):** the generic pieces this brief
> calls "the core" moved to the repository root as the `streamkit` library —
> `src/streamkit/render/png.py`, `src/streamkit/describe.py`, `src/streamkit/grid.py`,
> `src/streamkit/chat.py`, `src/streamkit/sources/`, `src/streamkit/sink.py`, plus the shared run loop
> (`streamkit/pipeline.py`) and CLI helpers (`streamkit/cli.py`). The medium's own pieces live here:
> `src/stream_in_novel/novel.py` (was `src/streamkit/novel.py`) and
> `src/stream_in_novel/sinks/novel.py` (was `src/streamkit/sinks/novel.py`). The command in the tasks
> below, `python -m streamkit …`, is now `stream-in-novel …` (or `python -m stream_in_novel`).

Run it:

```bash
# ~/.local/bin/agent on purpose: ~/.local/bin is NOT on PATH in a fresh WSL login shell.
# Repo stays on /mnt/c (slow in WSL, but the Windows-side tooling needs it there).
wsl.exe -d Ubuntu -- bash -lc 'cd /mnt/c/Users/AMD/Documents/00_Development_and_IT/stream && ~/.local/bin/agent -p --trust --model auto "$(cat plan-novel.md)"'
```

CORE STATUS — **the shared core already exists and is VERIFIED. Do not rebuild it, and do not edit
the ported modules.** Verified 2026-09-16: 36 tests green (Windows `pytest`, the project venv on
numpy 2.4.6, and WSL `unittest`), plus a live Twitch capture (64 frames @ 8.1 fps).
**Stay inside the files this brief names.**

WHAT THE CORE GIVES YOU (all in `src/streamkit/`, editable-installed into `.venv`):

    from streamkit.grid import Grid                 # .rgb uint8 (h,w,3), .rgb_bytes, .index, .t, .meta
                                                   # .resize(w, h, method="area"|"nearest"), .save_ppm(path)
                                                   # .mean_abs_error(other) — frame-to-frame difference
    from streamkit.sink import register, build_sink # @register("name") on your Sink class
    from streamkit.sources import build_source      # pattern:bars|square|sweep|noise, file:<path>,
                                                   # url:<http...>, twitch:<channel>
    from streamkit.chat import TwitchChat, ChatMessage  # anonymous IRC (justinfan, no OAuth), .start(),
                                                   # .latest() -> list[ChatMessage], .status, .stop()
                                                   # also: format_chat_block(), prepare_chat_rows()
                                                   # (ChatRow(user, text, user_color)), user_rgb()
    from streamkit.ffmpeg import find_ffmpeg        # FFMPEG_PATH -> PATH -> WinGet dir

  * A sink is `open(width, height)` / `write(grid)` / `close()` (close must be idempotent). Put it in
    `src/streamkit/sinks/<name>.py` **and import it from `src/streamkit/sinks/__init__.py`**, or it
    never registers.
  * `build_sink(sink_name, **options)` — the first parameter is `sink_name`, NOT `name`: sinks take
    their own `name` option (default output filename) and the two would collide.
  * New CLI flags for your sink go in `_sink_options()` in `src/streamkit/cli.py`; the CLI passes no
    options to unknown sinks, so a sink needing options must be wired there (or take defaults).
    `_chat_channel_from_source(args.source)` already exists in `cli.py` — reuse it for chat.
  * Tests: write `unittest.TestCase` classes — **WSL has no pytest**. Run in WSL with
    `PYTHONPATH=src python3 -m unittest discover -s tests -t tests`; on Windows `python -m pytest -q`.
    Gate anything needing ffmpeg with `@unittest.skipUnless(has_ffmpeg(), ...)`.
  * CLI: `PYTHONPATH=src python3 -m streamkit --source … --size WxH --fps N --sink NAME --out PATH
    --seconds N --frames N --pace realtime|fast`. Use `--pace fast` in tests; `realtime` is the default.
  * Debug frames are binary PPM via `grid.save_ppm()` — **never add Pillow**; there is no PNG anywhere
    in this project *yet* (Task 2 below adds a stdlib one, and only inside `render/png.py`).
  * WSL has numpy + requests only (no ffmpeg, no streamlink, no API key). Live runs happen on
    the Windows host (`python`, ffmpeg 8.0.1) or in the project venv (`.venv/Scripts/python`,
    streamlink 8.6.1).
  * `render/terminal.py`, `sources/twitch.py` and `sources/ffmpeg_source.py`
    are verbatim ports of stream-in-terminal (hashes matched) — read them, never edit them. One
    documented deviation: `ffmpeg_source.py` sends `-headers` only for http(s) URLs, because ffmpeg
    8.x rejects it for local files.

---

CONTEXT — Repo: `C:\Users\AMD\Documents\00_Development_and_IT\stream` (WSL:
`/mnt/c/Users/AMD/Documents/00_Development_and_IT/stream`), package `streamkit`. Goal: **the medium is
language.** Every X seconds the pipeline hands a still frame plus the recent Twitch chat to a
vision-language model, which writes the next 2–4 sentences of a continuing story; the terminal
updates live with the prose (and, in a lower pane, the chat that fed it), and the whole run is saved
as a readable novel. A stream becomes slow television you *read*. The register can be a literary
novel, a nature documentary about a human at a keyboard, or hard-boiled noir — same mechanism, three
prompt presets.

DESIGN PLACEMENT (important):

1. This **is a sink** (the medium is prose), so `write(grid)` must stay cheap and must never block on
   the network. All model calls happen on a **single background worker thread**; if a request is in
   flight when the next interval elapses, the sink *skips* (it does not queue) — the frame is only a
   snapshot of "now", so a late description of an old frame is worthless.
2. The model call sits behind a small **describer seam** (`Describer` protocol), exactly like the FX
   purity rule: `describe(prompt, png_bytes, stream=True) -> Iterator[str]`. Real implementation is
   one OpenAI-compatible HTTP path; tests inject a `ScriptedDescriber`. Determinism for tests lives
   behind that seam, never in the sink.
3. Prompt assembly and story-continuity are **pure functions** over plain data (previous paragraphs +
   chat lines + scene-change flag) → a `(system, user)` prompt pair. Unit-test them with no network.

MECHANISM (already designed — implement this, don't redesign it):

  * **Capture resolution.** This is the one place the "grid is small" convention is deliberately
    broken: the terminal pixel-art sink wants ~160x48, but a VLM cannot describe the scene from a
    160x48 mosaic — that is ~115x40 upscaled, i.e. a colour blot. Run the novel sink at
    `--size 640x360 --fps 2` (RGB 691 kB/frame, ~1.4 MB/s through the pipe — trivial). Document this
    in the README as a per-sink consideration, not a core change.
  * **Interval.** `--novel-interval` seconds between model calls, default **15**. A streaming reply
    runs 2–6 s for ~60 words, so 15 s leaves headroom; assert in a test that the sink never has more
    than one request in flight.
  * **Change gate.** Skip a call when the frame is nearly identical to the last described frame
    (`grid.mean_abs_error(last) < --novel-change-threshold`, default 1.5) unless the chat produced new
    lines — a static title card should not generate 40 paragraphs of filler. This is the single
    biggest quality-and-cost lever.
  * **Story context.** Carry the **last 3 paragraphs verbatim** into the prompt plus the last 8 chat
    lines, and instruct: *continue the story; never restate; 2–4 sentences*. Repetition is the known
    failure mode of frame-at-a-time captioning with continuity bolted on.
  * **Chat is dialogue, not a ticker.** Chat users are characters: quote their lines in the prose and
    use their names. `--novel-no-chat` disables it; the chat channel is derived from the source with
    the existing `_chat_channel_from_source()`.
  * **Language.** `--novel-lang` in `pt-BR|en|auto`, default `pt-BR` (the streaming channels this is
    aimed at, e.g. `oMeiaUm`, chat in Portuguese). `auto` = "the dominant language of the chat,
    Portuguese if unclear".
  * **Styles.** `--novel-style` in `novel|nature|noir`, default `novel`. Three short system prompts.
  * **Transcript.** Append each finished paragraph to `--out` (default `out/novel/<channel>-<date>.md`,
    header = channel, start time, style) so a run yields a file you can actually read afterwards.
  * **Backend flags.** `--novel-base-url` (default `https://api.deepseek.com`), `--novel-model`
    (default `deepseek-v4-flash-vision-exp`), `--novel-key` falling back to `$DEEPSEEK_API_KEY` then
    `$NOVEL_API_KEY`. The same OpenAI-compatible path must also work against a local Ollama
    (`--novel-base-url http://127.0.0.1:11434/v1 --novel-model qwen3-vl:8b`) with no code change.
  * **HTTP.** Use **stdlib `urllib.request`**, not `requests`-only code, and keep numpy the only new
    dependency. POST `{model, messages:[{role:"user",content:[{type:"text",...},{type:"image_url",
    image_url:{url:"data:image/png;base64,..."}}]}], stream:true, temperature:1.1, max_tokens:180}`.
    Parse SSE lines (`data: {...}` → `choices[0].delta.content`), stopping at `[DONE]`. Real numbers
    for the budget: ~384 tokens per image + ~700 tokens of prompt/context in, ~120 out; at the
    published V4-Flash flash rates that is ≈$0.0003 per call ≈ **$0.08/hour** off-peak ($0.15/h peak)
    at one call per 15 s. Report measured numbers anyway.

ENVIRONMENT: you run in WSL Ubuntu — python3 3.10.12, numpy 1.26.4, requests; **NO ffmpeg, NO Pillow,
NO streamlink, no API key, and no network egress you may rely on.** So every test is offline and uses
`pattern:*` sources plus the `ScriptedDescriber`. The Windows host (ffmpeg 8.0.1, streamlink 8.6.1 in
`.venv`, `DEEPSEEK_API_KEY`) is where live runs and real model calls happen — mark clearly who ran
what, and write down commands you could not execute instead of implying you ran them.

REMAINING TASKS:

1. **GATE — does the vision model actually describe a Twitch frame usefully? (Windows host; ~10
   minutes; report and STOP if the answer is no.)**
   Get three real stills from **one connection, spaced by real wall-clock time**:
   ```bash
   URL=$(timeout 45 .venv/Scripts/python -m streamlink --stream-url twitch.tv/<live-channel> best | tr -d '\r\n')
   ffmpeg -y -i "$URL" -vf "scale=640:-2,fps=1/8" -frames:v 3 out/novel/seq%d.png
   ```
   **Do NOT use `-ss N -i "$URL"` for this.** Verified on this host 2026-09-16: `-ss` past the live
   window start clamps and returns the same segment twice — `still2.png` and `still3.png` came out
   byte-identical (`md5 d50b4375…`) while the `fps=1/8` sequence gave three distinct frames
   (`b6c03f1e`, `bea924ab`, `3005f236`). That is also why the sink must take a *live* snapshot per
   call rather than seek.

   Measured that same day (640x360): PNGs of 105–198 kB raw → **128–258 kB as base64** per
   still, i.e. ≈17 kB/s of upload at one call per 15 s. The frame is legible enough to narrate: the
   sample stills showed a ship on dark water at night, a facecam of a person in a headset, a sponsor
   bug, and a Portuguese in-game clock reading `Sexta-feira, dia 26 / 21:35`. Confirm the same by
   eye before spending a token.

   Then one `curl` to `https://api.deepseek.com/chat/completions` with
   `model=deepseek-v4-flash-vision-exp` and a base64 `data:image/png;base64,...` block carrying the
   *actual* Task 4 system prompt (write it first, even roughly). Report **verbatim** model output for
   all three, the latency of each call, and whether the stream's scene/talking-head/UI is described
   specifically or as generic mush. **GATE: if the output is interchangeable between two different
   channels, that is a FINDING — report it and stop; do not build a sink around a capability that
   isn't there.** Do not skip to Task 5 because a test suite is green.
2. `src/streamkit/render/png.py` — a **stdlib-only PNG encoder** (no Pillow, ever): `write_png(path,
   rgb: bytes, width, height)` and `png_bytes(rgb, width, height) -> bytes`, using `zlib.compress`
   and filter type 0 rows, with correct IHDR/IDAT/IEND chunks and CRCs. Grayscale-free, RGB8 only.
   ~40 lines. (PPM is not accepted by the API; that is the only reason this file exists.)
3. `src/streamkit/describe.py` — the describer seam:
   - `Describer` Protocol: `describe(*, system: str, user: str, image_png: bytes, on_token=None) -> str`.
   - `OpenAICompatDescriber(base_url, model, api_key, timeout=30.0, temperature=1.1, max_tokens=180)`:
     stdlib `urllib.request`, SSE streaming, tokens delivered through `on_token` as they arrive, full
     text returned; on HTTP error raise `DescribeError` carrying status + body (never a bare
     traceback); one retry on timeout/5xx with backoff, then give up quietly (the story simply pauses).
   - `ScriptedDescriber(paragraphs)` — offline, returns canned text, can be told to sleep to simulate
     latency, records every prompt it was given (the tests assert on those prompts).
   - `NullDescriber` — always returns "" (lets the sink run with no key at all; the terminal then shows
     the chat pane and a "no describer" notice instead of prose).
4. `src/streamkit/novel.py` — pure story logic, no I/O:
   - `StoryState`: `paragraphs: list[str]` (rolling, keep ≥5), `add(paragraph)`, `tail(n)`.
   - `build_prompt(state, chat_lines, style, lang, channel) -> tuple[str, str]` — the system prompt per
     style (**`novel`**: literary third-person past tense, ongoing chapter; **`nature`**: a nature
     documentary observing a human at a keyboard; **`noir`**: hard-boiled detective, second person)
     plus the language rule, the "continue, never restate, 2–4 sentences" rule, the "chat users are
     characters, quote them by name" rule, and the ban on mentioning images, cameras, AI, timestamps or
     technical terms. The user message is the tail paragraphs + the recent chat lines + "continue".
   - `should_describe(prev_grid, grid, chat_lines, last_chat_count, threshold) -> bool` — the change
     gate, pure and testable.
5. `src/streamkit/sinks/novel.py` — `@register("novel")` (ANSI live view) and
   `@register("novel_txt")` (plain text to stdout/file, no escapes — the pipe-friendly, CI-testable
   one). Both share the worker thread, the interval, the change gate, transcript appending and
   `close()` idempotence; they differ only in rendering:
   - ANSI view: alternate screen buffer on open, cursor hidden, restored and idempotent on close;
     upper pane = the novel, word-wrapped to `shutil.get_terminal_size().columns`, bottom-anchored so
     new sentences scroll in as they stream; lower pane = last 4 chat rows via
     `prepare_chat_rows()`/`format_chat_block()` (coloured names come free); one status line
     (style, language, calls made, seconds to the next call, chat status). Degrade gracefully on tiny
     terminals (≥40x10) and to ASCII box drawing when `--no-color`.
   - Wire every new flag through `_sink_options()` in `cli.py` (`novel_*` names), reuse
     `_chat_channel_from_source()`, start/stop `TwitchChat` in the sink, and honour `--seconds`/Ctrl+C.
6. Tests (offline, `unittest.TestCase` classes — WSL has no pytest), these are the acceptance criteria:
   - `test_novel_nonblocking.py`: `ScriptedDescriber` that sleeps 1.0 s per call; feed 30 frames of
     `pattern:bars` with `--pace fast` and `interval=0` — assert total `write()` time stays under
     200 ms, that at most one call is in flight, and that skipped intervals do not queue up;
   - `test_novel_change_gate.py`: 20 identical frames + no chat → exactly **one** describe call; then a
     frame that differs above threshold, or a new chat line, → exactly two;
   - `test_novel_prompt.py`: after three paragraphs, the prompt contains the last 3 (and not the 4th),
     the 8 most recent chat lines with their usernames, the style-specific instruction, and the
     language rule; `pt-BR` and `en` produce different prompts; `noir` ≠ `novel`;
   - `test_novel_png.py`: `png_bytes()` output starts with the PNG magic, the IHDR chunk reports the
     right width/height/bit-depth/colour-type (8/2), every chunk CRC verifies, and `zlib.decompress`
     of the concatenated IDATs yields exactly `height * (1 + 3 * width)` bytes with filter byte 0;
   - `test_novel_transcript.py`: paragraphs land in `--out` in order, one per line, with the header;
     `close()` twice is safe, appends rather than truncates on the second run, and the ANSI view
     restores the terminal (assert the save/restore escape sequence and the show-cursor code were
     written, in that order);
   - `test_novel_describe_error.py`: `OpenAICompatDescriber` against a `file://`/dead-port URL raises
     `DescribeError`, the sink survives it, keeps its frame loop running and reports the error in the
     status line (no traceback, no hang).
   → acceptance: `PYTHONPATH=src python3 -m unittest discover -s tests -t tests` — one clean run, zero
   ffmpeg, zero network, zero key. (Windows equivalent, also expected green: `python -m pytest -q`.)
7. Visual/live evidence:
   - offline, WSL: `python3 -m streamkit --source pattern:bars --size 640x360 --fps 2 --sink novel_txt
     --novel-interval 1 --novel-describer scripted --seconds 10` → report the paragraph count and paste
     two of the scripted paragraphs as proof the loop appends in order;
   - on the Windows host (you may not be able to run this — if so, write the command and say so):
     `.venv/Scripts/python -m streamkit --source twitch:oMeiaUm --size 640x360 --fps 2 --sink novel
     --novel-interval 15 --novel-style novel --novel-lang pt-BR --out out/novel/omeiaum.md --seconds 180`
     → report frames captured, real describe-call count, median call latency, and paste the **first 200
     characters of the real transcript**. Never claim a capture you did not make.
8. README: a short "Novel" section — the mechanism, the flag table, the capture-resolution note (why
   640x360 is not a contradiction of the grid contract), the cost-per-hour figure from Task 1's real
   measurements, the style presets, and the honest limitation that the prose is only as good as the
   model's read of a 640x360 still every 15 s.

GUARDRAILS:
- `write(grid)` does no I/O and never blocks: no HTTP, no file writes, no `time.sleep` on the caller's
  thread. Only the worker thread talks to the model and the transcript file.
- No new dependencies: stdlib (`urllib`, `zlib`, `threading`, `textwrap`, `shutil`) + the existing
  numpy. **Do not add Pillow, requests-only code, openai, or aiohttp.**
- Never break the core: `write()` semantics, the sink registry and `build_sink(sink_name, …)`
  keep their exact meaning, and the rest of the test suite must stay green in the same run.
- The model never sees a key in logs, the transcript, or the status line; `--novel-key` beats the env
  var, and the key is never echoed.
- Do not edit this plan file. Do not commit. Do not modify `stream-in-terminal`.
- If the Task 1 gate fails, that is a FINDING: report the verbatim output and stop. Do not paper over
  generic prose with prompt-tuning theatre, and do not tune prompts silently until a test passes.
- Honesty: separate "verified offline in WSL" from "needs the Windows host and a key". Report real
  measured latency, call counts and file sizes — not "works".

REPORT BACK: files created (paths); verbatim test tail; the exact acceptance commands and their real
output; Task 1's three verbatim model outputs with per-call latency and the exact prompt used; the
real transcript excerpt if you produced one; measured per-call cost/token counts if you could measure
them; and any place this brief was wrong.
