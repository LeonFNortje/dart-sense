#!/usr/bin/env bash
# Start Dart Sense: sets up the virtual environment on first run (or when requirements.txt changes),
# then launches the web app. Extra arguments are passed to play/app.py, e.g. ./start.sh --no-window
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

VENV=.venv
PYTHON_VERSION=3.14
REQUIREMENTS=play/requirements.txt
STAMP="$VENV/.requirements.sha256"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
    echo "Creating virtual environment ($VENV, Python $PYTHON_VERSION)..."
    uv venv --python "$PYTHON_VERSION" "$VENV"
fi

wanted="$(sha256sum "$REQUIREMENTS" | cut -d' ' -f1)"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$wanted" ]; then
    echo "Installing dependencies..."
    uv pip install --python "$VENV/bin/python" -r "$REQUIREMENTS"
    echo "$wanted" > "$STAMP"
fi

# score calling needs eSpeak NG; the app still runs without it
if ! command -v espeak-ng >/dev/null 2>&1; then
    echo "Note: espeak-ng not found, scores won't be called out (Arch: sudo pacman -S espeak-ng)" >&2
fi

exec "$VENV/bin/python" play/app.py "$@"
