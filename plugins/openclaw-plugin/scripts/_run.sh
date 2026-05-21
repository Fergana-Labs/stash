#!/usr/bin/env bash
# Re-exec a plugin hook script under the python that has stashai installed.
#
# When stashai ships via pipx or uv, the package lives in an isolated venv.
# Resolve the `stash` binary's symlink to find that venv, then use its python.
# Falls back to STASH_PYTHON or system python3 for manual installs.
set -euo pipefail

SCRIPT="$1"
shift
TARGET="$(dirname "$0")/$SCRIPT.py"

if [ "$SCRIPT" = "on_session_start" ]; then
  command -v uv >/dev/null 2>&1 && uv tool upgrade --quiet stashai >/dev/null 2>&1 &
fi

PY="${STASH_PYTHON:-}"
if [ -z "$PY" ] && command -v stash >/dev/null 2>&1; then
  STASH_REAL="$(python3 -c "import os, shutil; print(os.path.realpath(shutil.which('stash')))" 2>/dev/null || true)"
  if [ -n "$STASH_REAL" ]; then
    CANDIDATE="$(dirname "$STASH_REAL")/python"
    if [ -x "$CANDIDATE" ]; then
      PY="$CANDIDATE"
    fi
  fi
fi

if [ -z "$PY" ]; then
  PY="python3"
fi

exec "$PY" "$TARGET" "$@"
