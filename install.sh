#!/usr/bin/env bash
# joinstash.ai/install — install the stashai CLI and run the interactive
# `stash login` setup wizard (managed-vs-self-host, browser auth,
# upload-vs-read, agent hooks, repo connection).
#
# Recommended invocation (keeps stdin attached to your terminal so the
# questionnaire's interactive picker works):
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"
#
# If no Python toolchain is present, the script
# bootstraps `uv` (a single Rust binary) which downloads the right Python
# version automatically.

# Re-run safe (idempotent): if stashai is already installed, the picked
# package manager will upgrade it to the latest version.
set -euo pipefail

PACKAGE="${STASH_INSTALL_PACKAGE:-stashai}"

require_tty() {
  if [ -t 0 ]; then
    return
  fi

  cat >&2 <<'MSG'
stash needs an interactive terminal for setup.
Re-run with this form:

  bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"

MSG
  exit 1
}

require_tty

if command -v uv >/dev/null 2>&1; then
  INSTALLER="uv"
  INSTALL_CMD=(uv tool install --force --reinstall --refresh "$PACKAGE")
else
  printf '→ Installing uv (manages Python for you)…\n'
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
  INSTALLER="uv"
  INSTALL_CMD=(uv tool install --force --reinstall --refresh "$PACKAGE")
fi

printf '→ Installing %s via %s…\n' "$PACKAGE" "$INSTALLER"
"${INSTALL_CMD[@]}" >/dev/null 2>&1

# uv puts binaries in ~/.local/bin. If the shell hasn't picked up PATH yet,
# surface the fix instead of silently failing.
if ! command -v stash >/dev/null 2>&1; then
  cat >&2 <<'MSG'
stash installed, but it isn't on PATH yet. Add this to your shell rc and
re-open the terminal (or `source` your rc):

  export PATH="$HOME/.local/bin:$PATH"

Then re-run: curl -fsSL https://joinstash.ai/install | bash
MSG
  exit 1
fi

# Stdin is a real terminal — hand off to the questionnaire. `stash login`
# asks scope, managed-vs-self-host, browser sign-in, workspace, and the
# Claude Code plugin install (when detected).
exec stash login
