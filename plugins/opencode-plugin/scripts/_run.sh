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

if [ "$SCRIPT" = "on_session_start" ]; then
  command -v uv >/dev/null 2>&1 && uv tool install --quiet stashai@latest >/dev/null 2>&1 &
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$SCRIPT_DIR/$SCRIPT.py"

REPO_ROOT=""
case "$SCRIPT_DIR" in
  */stashai/plugin/assets/*/scripts)
    REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
    ;;
  */plugins/*-plugin/scripts)
    REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    ;;
esac
if [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT/stashai" ] && [ -d "$REPO_ROOT/cli" ]; then
  export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
fi

PY=""
if command -v stash >/dev/null 2>&1; then
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
