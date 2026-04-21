#!/usr/bin/env bash
# joinstash.ai/install — install the stashai CLI and run the interactive
# `stash connect` questionnaire (scope, managed-vs-self-host, browser auth,
# workspace, agent plugin).
#
# Recommended invocation (keeps stdin attached to your terminal so the
# questionnaire's interactive picker works):
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"
#
# `curl … | bash` works for the install part but the interactive picker
# needs a real terminal on stdin — bash's `| bash` makes the script body
# stdin instead. We try to detect that case and surface an actionable
# message rather than crashing inside questionary.
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

Then re-run: curl -fsSL https://joinstash.ai/install | bash
MSG
  exit 1
fi

# If stdin isn't a terminal, the user piped us via `curl … | bash`. The
# /dev/tty redirect trick to recover interactivity hits a Python 3.14 +
# macOS asyncio kqueue bug (OSError EINVAL on add_reader for the
# redirected fd). The reliable fix is the `bash -c "$(curl ...)"` form
# which keeps stdin as the natural terminal — surface the right command
# instead of crashing inside questionary.
if [ ! -t 0 ]; then
  cat >&2 <<'MSG'
stash is installed, but the setup wizard needs an interactive terminal.
Re-run with this form (it keeps stdin attached to your shell):

  bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"

Or just run it now:

  stash connect

MSG
  exit 0
fi

# Stdin is a real terminal — hand off to the questionnaire. `stash connect`
# asks scope, managed-vs-self-host, browser sign-in, workspace, and the
# Claude Code plugin install (when detected).
exec stash connect
