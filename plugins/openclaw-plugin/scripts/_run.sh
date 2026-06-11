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
  command -v uv >/dev/null 2>&1 && uv tool install --quiet stashai@latest >/dev/null 2>&1 &
fi

PY="${STASH_PYTHON:-}"
if [ -z "$PY" ] && command -v stash >/dev/null 2>&1; then
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

if [ -z "$PY" ]; then
  PY="python3"
fi

exec "$PY" "$TARGET" "$@"
