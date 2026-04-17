#!/usr/bin/env bash
# stash.ac/install — install the stashai CLI and run the interactive
# `stash connect` questionnaire (scope, managed-vs-self-host, browser auth,
# workspace, agent plugin).
#
# Usage:
#   curl -fsSL https://stash.ac/install | bash
#
# Re-run safe (idempotent): if stashai is already installed, the picked
# package manager will upgrade it to the latest version.
set -euo pipefail

PACKAGE="stashai"

if command -v pipx >/dev/null 2>&1; then
  INSTALLER="pipx"
  INSTALL_CMD=(pipx install "$PACKAGE" --force)
elif command -v uv >/dev/null 2>&1; then
  INSTALLER="uv"
  INSTALL_CMD=(uv tool install "$PACKAGE" --force)
elif command -v pip3 >/dev/null 2>&1; then
  INSTALLER="pip3"
  INSTALL_CMD=(pip3 install --user --upgrade "$PACKAGE")
else
  cat >&2 <<'MSG'
stash needs a Python package manager to install. None found on PATH.

Pick one and re-run:
  brew install pipx          # macOS / Homebrew
  python3 -m pip install pipx
  curl -LsSf https://astral.sh/uv/install.sh | sh    # uv
MSG
  exit 1
fi

printf '→ Installing %s via %s…\n' "$PACKAGE" "$INSTALLER"
"${INSTALL_CMD[@]}" >/dev/null

# pipx + uv put binaries in ~/.local/bin; pip --user puts them somewhere
# similar. If the shell hasn't picked up PATH yet, surface the fix instead
# of silently failing.
if ! command -v stash >/dev/null 2>&1; then
  cat >&2 <<'MSG'
stash installed, but it isn't on PATH yet. Add this to your shell rc and
re-open the terminal (or `source` your rc):

  export PATH="$HOME/.local/bin:$PATH"

Then re-run: curl -fsSL https://stash.ac/install | bash
MSG
  exit 1
fi

# Hand off to the questionnaire. `stash connect` asks scope, managed-vs-
# self-host, browser sign-in, workspace, and Claude Code plugin install
# (when detected).
#
# When the script runs via `curl … | bash`, our stdin is the script body,
# so questionary aborts with "Input is not a terminal". Re-attach stdin
# to the controlling terminal before exec'ing if /dev/tty is available
# (interactive shells); fall back to plain exec otherwise (CI, Docker
# without -it — those will just hit the same questionary error, which is
# the right signal that this isn't an interactive context).
if [ -r /dev/tty ] && [ -w /dev/tty ]; then
  exec </dev/tty stash connect
else
  exec stash connect
fi
