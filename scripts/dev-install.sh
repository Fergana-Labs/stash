#!/usr/bin/env bash
# Reinstall stashai from local source and wipe cached configs so the next
# `stash` run starts from a clean slate (fresh endpoint, fresh auth).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "→ pipx install --force $REPO_ROOT"
pipx install --force "$REPO_ROOT"

for cfg in "$HOME/.stash/config.json" "$PWD/.stash/config.json"; do
  if [ -f "$cfg" ]; then
    echo "→ removing $cfg"
    rm "$cfg"
  fi
done

echo "✓ done — run \`stash connect\` to re-auth"
