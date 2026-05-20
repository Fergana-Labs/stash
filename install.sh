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
FUSE_T_VERSION="1.2.6"
FUSE_T_SHA256="fcfd95e4c09fb1f90efa134ef9b328b5757c59b43d6c7c23384a6a7001db4eb3"
FUSE_T_PKG_URL="https://github.com/macos-fuse-t/fuse-t/releases/download/${FUSE_T_VERSION}/fuse-t-macos-installer-${FUSE_T_VERSION}.pkg"
STASH_INSTALL_TMP_DIRS=()

cleanup() {
  for dir in "${STASH_INSTALL_TMP_DIRS[@]}"; do
    rm -rf "$dir"
  done
}
trap cleanup EXIT

fail() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

require_tty() {
  if [ -t 0 ]; then
    return
  fi

  cat >&2 <<'MSG'
stash needs an interactive terminal for setup and filesystem-provider install.
Re-run with this form:

  bash -c "$(curl -fsSL https://raw.githubusercontent.com/Fergana-Labs/stash/main/install.sh)"

MSG
  exit 1
}

ensure_sudo() {
  if sudo -n true >/dev/null 2>&1; then
    return
  fi
  printf '→ Administrator access is needed to install the Stash filesystem provider.\n'
  sudo -v
}

have_macos_fuse_provider() {
  pkgutil --pkgs | grep -Eq '^org\.fuse-t\.' &&
    [ -f /usr/local/lib/libfuse-t.dylib ]
}

install_macos_fuse_provider() {
  if have_macos_fuse_provider; then
    printf '→ Stash filesystem provider already installed.\n'
    return
  fi

  ensure_sudo
  tmp_dir="$(mktemp -d)"
  STASH_INSTALL_TMP_DIRS+=("$tmp_dir")
  pkg_path="${tmp_dir}/fuse-t.pkg"

  printf '→ Installing Stash filesystem provider for macOS…\n'
  curl -fsSL "$FUSE_T_PKG_URL" -o "$pkg_path"
  actual_sha="$(shasum -a 256 "$pkg_path" | awk '{print $1}')"
  if [ "$actual_sha" != "$FUSE_T_SHA256" ]; then
    fail "FUSE-T package checksum mismatch"
  fi
  sudo installer -pkg "$pkg_path" -target / >/dev/null

  if ! have_macos_fuse_provider; then
    fail "FUSE-T installation completed, but libfuse-t.dylib was not found"
  fi
}

have_linux_fuse_provider() {
  [ -e /dev/fuse ] || return 1
  command -v fusermount >/dev/null 2>&1 || return 1

  if command -v ldconfig >/dev/null 2>&1 &&
    ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2'; then
    return 0
  fi

  for path in \
    /lib/libfuse.so.2 \
    /lib/*/libfuse.so.2 \
    /usr/lib/libfuse.so.2 \
    /usr/lib/*/libfuse.so.2 \
    /usr/local/lib/libfuse.so.2; do
    if [ -e "$path" ]; then
      return 0
    fi
  done

  return 1
}

install_linux_fuse_provider() {
  if have_linux_fuse_provider; then
    printf '→ Stash filesystem provider already installed.\n'
    return
  fi

  ensure_sudo
  printf '→ Installing Stash filesystem provider for Linux…\n'
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y fuse libfuse2
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y fuse fuse-libs
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y fuse fuse-libs
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm fuse2
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper --non-interactive install fuse libfuse2
  else
    fail "unsupported Linux package manager for Stash filesystem provider"
  fi

  if ! have_linux_fuse_provider; then
    fail "FUSE installation completed, but /dev/fuse, fusermount, or libfuse.so.2 is missing"
  fi
}

install_fuse_provider() {
  case "$(uname -s)" in
    Darwin)
      install_macos_fuse_provider
      ;;
    Linux)
      install_linux_fuse_provider
      ;;
    *)
      fail "stash mount currently supports macOS and Linux"
      ;;
  esac
}

require_tty
install_fuse_provider

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

if ! stash mount --check >/dev/null; then
  fail "Stash CLI installed, but the filesystem provider could not be loaded"
fi

# Stdin is a real terminal — hand off to the questionnaire. `stash login`
# asks scope, managed-vs-self-host, browser sign-in, workspace, and the
# Claude Code plugin install (when detected).
exec stash login
