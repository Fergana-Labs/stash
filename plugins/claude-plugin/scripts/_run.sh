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

# On session start, upgrade the stashai package in the background. The hook
# scripts themselves only update through Claude Code's marketplace refresh
# (keyed off the plugin version bump) — the cache is a plain copy, not a git
# checkout, so there is nothing to pull here.
if [ "$SCRIPT" = "on_session_start" ]; then
  command -v uv >/dev/null 2>&1 && uv tool install --quiet stashai@latest >/dev/null 2>&1 &
fi

PY=""
if command -v stash >/dev/null 2>&1; then
  # Resolve with bash's own PATH lookup, then only use python to follow the
  # symlink. shutil.which inside python3 is wrong here: when python3 is a
  # pyenv shim, pyenv prepends its version's bin dir to PATH, so a stale
  # pip-installed `stash` in that dir shadows the real pipx/uv install.
  STASH_BIN="$(command -v stash)"
  STASH_REAL="$(python3 -c "import os, sys; print(os.path.realpath(sys.argv[1]))" "$STASH_BIN" 2>/dev/null || true)"
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
