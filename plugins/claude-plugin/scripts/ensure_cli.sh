#!/usr/bin/env bash
# Bring the stash CLI up to the version this plugin's hooks require.
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
# Writes only to stderr: stdout belongs to the hook's JSON payload.

set -uo pipefail

# The first release whose `stash hook run` accepts the `claude` agent. Raise
# this only when hooks.json starts depending on a newer CLI contract.
MIN_VERSION="0.1.318"

# True when $1 is an older dotted version than $2. An absent version reads as
# 0.0.0, so a missing CLI takes the upgrade path.
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

# Hooks run with a minimal PATH, so PATH alone is not enough to find uv.
# install.sh puts it in ~/.local/bin.
find_uv() {
  command -v uv 2>/dev/null && return 0
  [ -x "$HOME/.local/bin/uv" ] && echo "$HOME/.local/bin/uv" && return 0
  return 1
}

installed_version() {
  stash --version 2>/dev/null | awk '{print $2}'
}

UV="$(find_uv)" || UV=""
CURRENT="$(installed_version)"

if ! version_below "$CURRENT" "$MIN_VERSION"; then
  # New enough to run the hooks. Refresh in the background so the scripts
  # inside the package keep pace with the plugin, and never block the session.
  # All three fds are detached: a background job that inherits the hook's
  # stdout holds that pipe open, and the agent waits on it for the whole
  # upgrade — which is the stall this backgrounding exists to avoid.
  if [ -n "$UV" ]; then
    "$UV" tool install --quiet stashai@latest </dev/null >/dev/null 2>&1 &
  fi
  exit 0
fi

if [ -z "$UV" ]; then
  echo "stash: CLI ${CURRENT:-not found} is older than $MIN_VERSION and uv is not" \
       "installed, so it cannot upgrade itself. Session activity is not being" \
       "recorded. Reinstall with: curl -LsSf https://joinstash.ai/install.sh | sh" >&2
  exit 1
fi

# Synchronous: this session's remaining hooks need the upgraded CLI.
if ! "$UV" tool install --quiet stashai@latest >/dev/null 2>&1; then
  echo "stash: could not upgrade the CLI from $CURRENT to $MIN_VERSION or newer." \
       "Session activity is not being recorded." \
       "Try: uv tool install stashai@latest --force" >&2
  exit 1
fi

CURRENT="$(installed_version)"
if [ -z "$CURRENT" ]; then
  echo "stash: upgraded the CLI, but \`stash\` is not on PATH for hooks." \
       "Session activity is not being recorded." \
       "Add uv's tool directory (usually ~/.local/bin) to PATH." >&2
  exit 1
fi
if version_below "$CURRENT" "$MIN_VERSION"; then
  echo "stash: CLI upgrade did not reach $MIN_VERSION (still $CURRENT)." \
       "Session activity is not being recorded." \
       "Try: uv tool install stashai@latest --force" >&2
  exit 1
fi
