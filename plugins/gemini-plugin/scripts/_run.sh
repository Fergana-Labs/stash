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
  # Find the interpreter that can import stashai. On Unix the pipx/uv shim is a
  # symlink, so the venv python sits next to the resolved binary. On Windows the
  # shim is a real .exe (not a symlink), so realpath stays in the shim dir and we
  # also probe the uv tool venv. The path work is done in python because bash
  # mishandles Windows backslash paths, and we only accept an interpreter that
  # can actually import stashai — so we never silently pick the wrong one.
  PY="$(python3 - "$STASH_BIN" <<'PY_EOF' 2>/dev/null || true
import os, sys, shutil, subprocess
stash = os.path.realpath(sys.argv[1])
d = os.path.dirname(stash)
cands = [os.path.join(d, "python"), os.path.join(d, "python.exe"),
         os.path.join(d, "Scripts", "python.exe")]
uv = shutil.which("uv")
if uv:
    try:
        td = subprocess.run([uv, "tool", "dir"], capture_output=True,
                            text=True, timeout=5).stdout.strip()
    except Exception:
        td = ""
    if td:
        cands += [os.path.join(td, "stashai", "bin", "python"),
                  os.path.join(td, "stashai", "Scripts", "python.exe")]
for c in cands:
    if not os.path.exists(c):
        continue
    try:
        subprocess.run([c, "-c", "import stashai"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        continue
    print(c.replace(os.sep, "/"))
    break
PY_EOF
)"
fi

# pip --user (stashai on system site-packages) or any case the venv-python
# heuristic missed — fall through to whatever python3 is on PATH.
if [ -z "$PY" ]; then
  PY="python3"
fi

exec "$PY" "$TARGET" "$@"
