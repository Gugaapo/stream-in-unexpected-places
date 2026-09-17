#!/usr/bin/env bash
# Launch stream-in-terminal after checking external dependencies.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() {
  echo "error: $*" >&2
  exit 1
}

have() {
  command -v "$1" >/dev/null 2>&1
}

# Prefer project venv when present.
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
  # Ensure venv Scripts/bin tools are visible for streamlink checks.
  export PATH="${ROOT}/.venv/bin:${PATH}"
elif have python3; then
  PYTHON=python3
elif have python; then
  PYTHON=python
else
  die "Python 3 is required but was not found on PATH."
fi

"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "Python 3.10+ is required."

have ffmpeg || die "ffmpeg not found. Install ffmpeg and ensure it is on PATH."

# streamlink / yt-dlp: PATH or importable from the chosen Python
if ! have streamlink && ! have yt-dlp; then
  if ! "$PYTHON" -c 'import streamlink' >/dev/null 2>&1 \
     && ! "$PYTHON" -c 'import yt_dlp' >/dev/null 2>&1; then
    die "Need streamlink (preferred) or yt-dlp (pip install streamlink)."
  fi
fi

if "$PYTHON" -c 'import stream_in_terminal' >/dev/null 2>&1; then
  exec "$PYTHON" -m stream_in_terminal "$@"
fi

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "$PYTHON" -m stream_in_terminal "$@"
