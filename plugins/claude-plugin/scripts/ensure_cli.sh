#!/usr/bin/env bash
# Keep the stash CLI current enough to run this plugin's hooks.
#
# This script is the only upgrade path that reaches a stale install. The hook
# scripts themselves live inside the stashai package and run via
# `stash hook run`, which rejects unknown agents before executing anything — so
# an upgrade invoked from inside those scripts cannot run on exactly the
# versions that need it. The plugin auto-updates through Claude Code's
# marketplace, so CLI upgrades have to be driven from the plugin side of that
# boundary. Every other agent's hook config is written by the CLI itself, so
# their config and CLI always ship together and they have no such gap.
#
# This never blocks. The upgrade always runs detached, so a CLI below the floor
# costs this one session and the next session start finds the new CLI. Holding
# up session start while uv works is far more disruptive than losing one
# transcript, and users notice a stall immediately.
#
# Writes only to stderr: stdout belongs to the hook's JSON payload.

set -uo pipefail

# The first release whose `stash hook run` accepts the `claude` agent. Raise
# this only when hooks.json starts depending on a newer CLI contract.
MIN_VERSION="0.1.318"

# True when $1 is an older dotted version than $2. An absent version reads as
# 0.0.0, so a missing CLI counts as stale.
version_below() {
  awk -v have="$1" -v want="$2" 'BEGIN {
    n = split(have, h, "."); m = split(want, w, ".")
    for (i = 1; i <= 3; i++) {
      hi = (i <= n) ? h[i] + 0 : 0
      wi = (i <= m) ? w[i] + 0 : 0
      if (hi < wi) exit 0
      if (hi > wi) exit 1
    }
    exit 1
  }'
}

# Hooks run with a minimal PATH, so PATH alone is not enough to find uv. Checking
# only ~/.local/bin (where install.sh puts it) missed every user who had already
# installed uv another way — a Homebrew uv meant this script silently upgraded
# nothing, forever, with no output to say so.
find_uv() {
  command -v uv 2>/dev/null && return 0
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" \
                   /opt/homebrew/bin/uv /usr/local/bin/uv; do
    [ -x "$candidate" ] && echo "$candidate" && return 0
  done
  return 1
}

UV="$(find_uv)" || UV=""
CURRENT="$(stash --version 2>/dev/null | awk '{print $2}')"

# All three fds are detached: a background job that inherits the hook's stdout
# holds that pipe open, and the agent waits on it for the whole upgrade — which
# is the stall this backgrounding exists to avoid.
if [ -n "$UV" ]; then
  "$UV" tool install --quiet stashai@latest </dev/null >/dev/null 2>&1 &
fi

if ! version_below "$CURRENT" "$MIN_VERSION"; then
  exit 0
fi

# Below the floor: `stash hook run claude` would fail with a less useful
# message, so stop here and own the explanation. Exit 1 short-circuits the
# `&&` in hooks.json.
if [ -z "$UV" ]; then
  echo "stash: CLI ${CURRENT:-not found} is older than $MIN_VERSION and uv is not" \
       "installed, so it cannot upgrade itself. Session activity is not being" \
       "recorded. Reinstall with: curl -LsSf https://joinstash.ai/install.sh | sh" >&2
else
  echo "stash: CLI ${CURRENT:-not found} is older than $MIN_VERSION. An upgrade is" \
       "running in the background; this session is not recorded, the next one will be." >&2
fi
exit 1
