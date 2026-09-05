#!/bin/bash
set -u

BASE_DIR="$HOME/mri-cooling-camera"
EDGE_DIR="$BASE_DIR/edge"
PYTHON="$BASE_DIR/venv/bin/python3"

if [[ ! -x "$PYTHON" ]]; then
  printf 'Camera virtual environment is unavailable: %s\n' "$PYTHON" >&2
  exit 1
fi

cd "$EDGE_DIR" || exit 1
exec "$PYTHON" retry_failed_sessions.py
