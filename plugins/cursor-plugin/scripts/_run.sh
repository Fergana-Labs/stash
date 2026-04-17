#!/usr/bin/env bash
# Re-exec a plugin hook script under the python that has stashai installed.
#
# When stashai ships via pipx or uv (the install.sh defaults), the package
# lives in an isolated venv — the system `python3` (often a pyenv shim) can't
# import `stashai.plugin.*`, which breaks every plugin script. We resolve the
# `stash` binary's symlink to find the venv it lives in, then exec its
# python. Falls back to system `python3` for the plain `pip install --user`
# case where stashai is on the user's site-packages directly.
set -euo pipefail

SCRIPT="$1"
shift
TARGET="$(dirname "$0")/$SCRIPT.py"

PY=""
if command -v stash >/dev/null 2>&1; then
  STASH_REAL="$(python3 -c "import os, shutil; print(os.path.realpath(shutil.which('stash')))" 2>/dev/null || true)"
  if [ -n "$STASH_REAL" ]; then
    CANDIDATE="$(dirname "$STASH_REAL")/python"
    if [ -x "$CANDIDATE" ]; then
      PY="$CANDIDATE"
    fi
  fi
fi

# pip --user (stashai on system site-packages) or any case the venv-python
# heuristic missed — fall through to whatever python3 is on PATH.
if [ -z "$PY" ]; then
  PY="python3"
fi

exec "$PY" "$TARGET" "$@"
