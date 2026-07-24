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

# On session start, install the exact stashai version these scripts were built
# against (shipped alongside them in `stashai-version`). The hook scripts only
# update through Claude Code's marketplace refresh (keyed off the plugin version
# bump), so tracking `@latest` would let the library jump ahead of the cached
# scripts and break their imports. Pinning keeps library and scripts in lockstep.
if [ "$SCRIPT" = "on_session_start" ]; then
  PINNED_STASHAI="$(cat "$(dirname "$0")/stashai-version" 2>/dev/null || true)"
  if command -v uv >/dev/null 2>&1 && [ -n "$PINNED_STASHAI" ]; then
    uv tool install --quiet "stashai==$PINNED_STASHAI" >/dev/null 2>&1 &
  fi
fi

PY=""
if command -v stash >/dev/null 2>&1; then
  # Resolve with bash's own PATH lookup, then only use python to follow the
  # symlink. shutil.which inside python3 is wrong here: when python3 is a
  # pyenv shim, pyenv prepends its version's bin dir to PATH, so a stale
  # pip-installed `stash` in that dir shadows the real pipx/uv install.
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

# No interpreter that can import stashai means nothing can upload. Exec'ing a
# bare python3 here would "work" whenever some stale site-packages copy is
# importable — old client code against a new API, failing silently on every
# hook (that exact path cost a machine a month of session uploads in June '26).
# Refuse loudly instead.
if [ -z "$PY" ]; then
  echo "stash plugin: no stashai install found — session activity is NOT uploading to Stash." \
    "Fix: uv tool install stashai" >&2
  exit 1
fi

exec "$PY" "$TARGET" "$@"
