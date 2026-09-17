# Writing a medium

A *medium* is one project that plays a live stream somewhere unexpected. This is how to build one on
top of `streamkit`.

Read this once end to end; then copy the worked example at the bottom and change the sink.

---

## The model

```
source  ->  Grid  ->  sink
```

- A **source** produces frames: `twitch:<channel>`, `file:<path>`, `url:<https…>`, or `pattern:<name>`
  (deterministic synthetic video — no ffmpeg, no network, which is what makes tests offline).
- A **Grid** is one RGB frame at a chosen resolution, plus `index` and `t` (seconds since start).
- A **sink** is your medium: anything that can receive a Grid. That is the only thing you have to
  write.

`streamkit` gives you the sources, the Grid, the sink registry, an optional run loop, the Twitch chat
client, a vision-model seam, renderers and a PNG encoder. It does **not** give you the medium — that
belongs in your project, under `scripts/<your-medium>/`.

## Setting up to develop

The library is never installed from PyPI (the name there is an unrelated project). Install it from
this repository's root, into the same virtualenv your medium will use:

```bash
cd scripts/<your-medium>
python -m venv .venv
.venv/Scripts/python -m pip install -e ../..     # 1. the library (local edits apply live)
.venv/Scripts/python -m pip install -e .         # 2. your medium
```

## 1. Write the sink

A sink is three methods. `open` is called once with the grid geometry the source will deliver,
`write` once per frame, `close` exactly once — including on errors and Ctrl+C — and must be
idempotent.

```python
from streamkit.grid import Grid
from streamkit.sink import register

@register("my_medium")
class MySink:
    def __init__(self, *, path: str = "out/thing", label: str = "") -> None:
        self.path = path
        self.label = label
        self.frames_written = 0

    def open(self, width: int, height: int) -> None:
        self.size = (width, height)          # geometry is fixed here and never changes

    def write(self, grid: Grid) -> None:
        ...                                  # one frame
        self.frames_written += 1

    def close(self) -> None:
        ...                                  # flush + release; safe to call twice
```

Rules that matter:

- **`write()` must be cheap and must never block on the network.** A stream frame is a snapshot of
  "now"; a slow `write` is a stream that drifts. For anything remote — an HTTP API, an upload, a
  spreadsheet batch — keep one background worker thread and skip beats you cannot serve (see
  `stream-in-novel`'s `_NovelEngine`: one worker, and a busy beat is skipped, never queued).
- **`close()` is your only guarantee of a finished artifact.** It runs when the run ends, when an
  exception escapes and when the user hits Ctrl+C. Finalise files there.
- **Register with `@register("name")`** and import your module from your package (e.g. from
  `sinks/__init__.py`), or the sink never registers.
- **`build_sink(sink_name, **options)`** — the first argument is deliberately not called `name`,
  because sinks commonly take their own `name`/`label` option for default output filenames.
- **Pick your own geometry expectations.** `ansi`/`ppm_seq` want a small grid (~160×48); a vision
  model needs ~640×360. That is a per-medium decision, passed as `--size`; it is not a library change.

## 2. Give it a CLI

You almost never write the run loop. `streamkit.cli` provides the core flags and the flow:

```python
import argparse, sys
from streamkit.cli import add_core_arguments, run_pipeline_from_args

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="stream-in-thing", description="…")
    add_core_arguments(parser)                       # --source --size --fps --quality --out
                                                     # --seconds --frames --pace --quiet …
    parser.add_argument("--every", type=float, default=1.0, help="…")
    args = parser.parse_args(argv)
    return run_pipeline_from_args(
        args,
        sink_name="my_medium",
        sink_kwargs=lambda source: {                 # the opened source is yours to inspect
            "path": args.out or "out/thing",
            "label": source.name,                    # e.g. "twitch:oMeiaUm"
        },
        prog="stream-in-thing",                      # prefixes the closing summary line
    )
```

`add_core_arguments` gives you `--source`, `--size WxH`, `--fps`, `--quality`, `--seed`, `--ffmpeg`,
`--out`, `--seconds`, `--frames`, `--pace realtime|fast` and `--quiet` — the same flags every medium
uses, so a user who learned one medium knows them all.

For a medium with its own player loop (its own layout, its own key handling) skip
`run_pipeline_from_args` and compose the pieces yourself:

```python
from streamkit.pipeline import run
from streamkit.sink import build_sink
from streamkit.sources import TwitchSource

source = TwitchSource("oMeiaUm", width=160, height=48, fps=12, quality="best")
source.open()                      # resolves the stream; raises StreamResolveError
for grid in source.frames():       # Grid objects, until the stream ends
    ...
source.stderr()                    # ffmpeg's stderr, after the loop, to explain a failure
source.close()
```

## 3. The pieces you can lean on

| Need | Use |
|------|-----|
| Frames | `PatternSource`, `FileSource`, `UrlSource`, `TwitchSource` (`streamkit.sources`) |
| The channel behind a source | `chat_channel(source)` — `None` for pattern/file/url |
| Pixel access | `grid.rgb` (numpy `(h, w, 3)` uint8), `grid.rgb_bytes`, `grid.resize(w, h, method="area"\|"nearest")`, `grid.mean_abs_error(other)`, `grid.t`, `grid.index`, `grid.meta` |
| Save a debug frame | `grid.save_ppm(path)` — stdlib, no Pillow anywhere in this project |
| Terminal chat | `TwitchChat` (anonymous IRC, no OAuth), `prepare_chat_rows`, `format_chat_block`, `user_rgb` |
| A vision model | `streamkit.describe`: `OpenAICompatDescriber` (stdlib urllib + SSE), `ScriptedDescriber` (offline), `NullDescriber`, `resolve_api_key`, `load_dotenv` |
| A still to send it | `streamkit.render.png.png_bytes(grid.rgb_bytes, w, h)` — stdlib PNG encoder |
| Terminal art | `streamkit.render.terminal` (`render_frame`, `pixel_dimensions`, `resize_rgb`, `RenderMode`) |
| ffmpeg | `streamkit.ffmpeg.find_ffmpeg()` |
| Pacing / limits / cleanup | `streamkit.pipeline.run` |

**The change gate is the cost lever.** If your medium calls a paid API, compare each frame with the
last one you sent (`grid.mean_abs_error(previous)`) and skip when nothing changed, unless the chat
moved. One medium of the family does exactly that and it is the difference between cents and dollars
per hour.

## 4. Package it

Mirror the existing mediums:

```
scripts/<your-medium>/
  pyproject.toml          [project] name = "stream-in-<medium>", console script -> your cli:main
  README.md               the script readme: how it works, install, every flag, examples, evidence, limits
  src/stream_in_<medium>/ __init__.py, cli.py, __main__.py, sinks/, <your logic>.py
  tests/                  offline tests
  .env.example            only if it needs a secret
```

`pyproject.toml`, the essentials:

```toml
[project]
name = "stream-in-thing"
requires-python = ">=3.10"
dependencies = ["numpy>=1.24"]        # streamkit comes from the repository root, not PyPI

[project.scripts]
stream-in-thing = "stream_in_thing.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

Make `__main__.py` a thin entry point that turns a missing library into one clear line instead of a
traceback (copy the pattern from either existing medium) — a fresh clone that forgot step 1 of the
install should not see a stack trace.

## 5. Test it offline

Tests must never touch the network, need no API key and (ideally) no ffmpeg — that is what the
`pattern:` sources and `ScriptedDescriber` are for. Style: `unittest.TestCase`, so the suite runs
under both `unittest discover` and `pytest`.

```python
import itertools
from streamkit.describe import ScriptedDescriber
from streamkit.sources.pattern import PatternSource

source = PatternSource("bars", width=32, height=18, fps=10)
sink = MySink(path="…/thing.out")
sink.open(32, 18)
for grid in itertools.islice(source.frames(), 10):
    sink.write(grid)
sink.close()
```

Worth testing, in this order: the artifact is correct (bytes/rows/paragraphs), the limits and
cleanup behave (`close()` twice is safe), and the failure path degrades without a traceback.
Gate anything needing ffmpeg behind `@unittest.skipUnless(...)`.

## 6. Worked example — `stream-in-csv`

A complete medium: frame statistics to a CSV, one row every `--every` seconds. No new dependencies,
no network, works offline against `pattern:` sources. This is verified output, not an illustration.

```python
"""stream-in-csv — the stream as a CSV of frame statistics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from streamkit.cli import add_core_arguments, run_pipeline_from_args
from streamkit.grid import Grid
from streamkit.sink import register


@register("csv")
class CsvSink:
    """Append one row per ``every`` seconds: time, mean RGB, brightness, motion."""

    def __init__(self, *, path: str = "out/stream.csv", every: float = 1.0, label: str = "") -> None:
        self.path = path
        self.every = max(0.0, float(every))
        self.label = label
        self._file = None
        self._next_due = 0.0
        self._previous: Grid | None = None
        self.frames_written = 0
        self.rows_written = 0

    def open(self, width: int, height: int) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "w", encoding="utf-8", newline="")
        self._file.write("t,mean_r,mean_g,mean_b,brightness,motion\n")
        self._next_due = 0.0
        self.size = (width, height)

    def write(self, grid: Grid) -> None:
        self.frames_written += 1
        if self._file is None or grid.t < self._next_due:
            return                                   # not due yet: cheap early exit
        self._next_due = grid.t + self.every
        means = grid.rgb.reshape(-1, 3).mean(axis=0)
        brightness = float(means.mean())
        motion = (
            float(grid.mean_abs_error(self._previous))
            if self._previous is not None and self._previous.rgb.shape == grid.rgb.shape
            else 0.0
        )
        self._previous = grid.copy()
        self._file.write(
            f"{grid.t:.2f},{means[0]:.1f},{means[1]:.1f},{means[2]:.1f},"
            f"{brightness:.1f},{motion:.2f}\n"
        )
        self._file.flush()
        self.rows_written += 1

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stream-in-csv", description="Write frame statistics from a stream to a CSV."
    )
    add_core_arguments(parser)
    parser.add_argument("--every", type=float, default=1.0, help="seconds between rows")
    args = parser.parse_args(argv)
    return run_pipeline_from_args(
        args,
        sink_name="csv",
        sink_kwargs=lambda source: {
            "path": args.out or "out/stream.csv",
            "every": args.every,
            "label": source.name,
        },
        prog="stream-in-csv",
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

```console
$ python example.py --source pattern:sweep --size 64x36 --fps 10 --seconds 3 --pace fast \
      --every 0.5 --out out/stream.csv
stream-in-csv: 30 frames in 0.02s (1875.0 fps) via csv -> out/stream.csv

$ cat out/stream.csv
t,mean_r,mean_g,mean_b,brightness,motion
0.00,74.1,71.8,71.8,72.6,0.00
0.50,74.1,73.0,71.8,73.0,24.35
1.00,74.2,74.2,71.9,73.4,24.36
1.50,73.0,74.1,71.8,73.0,24.36
2.00,71.8,74.1,71.8,72.6,24.35
2.50,71.8,74.1,73.0,73.0,24.35
```

Swap `pattern:sweep` for `twitch:oMeiaUm` and the same medium writes a CSV of a live stream — that is
the whole point of the library: the medium only had to describe *where the frames go*.

## Checklist before you publish a medium

- [ ] The sink is three methods, `close()` is idempotent, and `write()` never blocks on I/O.
- [ ] `--source/--size/--fps/--seconds/--frames/--pace` all work (`add_core_arguments`).
- [ ] `python -m pip install -e ../.. && python -m pip install -e .` is the documented install.
- [ ] `README.md`: what it is, how it works, install, a table of every flag, examples on `oMeiaUm`,
      real evidence (command + output), and the honest limits.
- [ ] Tests are offline, and pass under `python -m unittest discover -s tests -t tests`.
- [ ] Output lands in `out/` and secrets in `.env` (both already gitignored at the repo root).
- [ ] Nothing was added to the library that is really just this medium's business.
