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
MACFUSE_VERSION="5.2.0"
MACFUSE_SHA256="09a4b4c23c1930af45335fc119696797da41562dec1630602d2db637f4804f27"
MACFUSE_DMG_URL="https://github.com/macfuse/macfuse/releases/download/macfuse-${MACFUSE_VERSION}/macfuse-${MACFUSE_VERSION}.dmg"
STASH_INSTALL_TMP_DIRS=()
STASH_INSTALL_MOUNTPOINTS=()

cleanup() {
  for mountpoint in "${STASH_INSTALL_MOUNTPOINTS[@]}"; do
    hdiutil detach "$mountpoint" >/dev/null 2>&1 || true
  done
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
  pkgutil --pkgs | grep -q '^io\.macfuse\.installer\.components\.core$' &&
    [ -f /usr/local/lib/libfuse.2.dylib ] &&
    [ -x /Library/Filesystems/macfuse.fs/Contents/Resources/mount_macfuse ]
}

prepare_macos_mountpoint() {
  ensure_sudo
  sudo mkdir -p /Volumes/Stash
  sudo chown "$(id -u):$(id -g)" /Volumes/Stash
}

install_macos_fuse_provider() {
  if have_macos_fuse_provider; then
    printf '→ Stash filesystem provider already installed.\n'
    prepare_macos_mountpoint
    return
  fi

  ensure_sudo
  tmp_dir="$(mktemp -d)"
  STASH_INSTALL_TMP_DIRS+=("$tmp_dir")
  dmg_path="${tmp_dir}/macfuse.dmg"
  dmg_mount="${tmp_dir}/macfuse"
  mkdir -p "$dmg_mount"

  printf '→ Installing Stash filesystem provider for macOS…\n'
  curl -fsSL "$MACFUSE_DMG_URL" -o "$dmg_path"
  actual_sha="$(shasum -a 256 "$dmg_path" | awk '{print $1}')"
  if [ "$actual_sha" != "$MACFUSE_SHA256" ]; then
    fail "macFUSE package checksum mismatch"
  fi
  hdiutil attach "$dmg_path" -nobrowse -readonly -mountpoint "$dmg_mount" >/dev/null
  STASH_INSTALL_MOUNTPOINTS+=("$dmg_mount")
  sudo installer -pkg "$dmg_mount/Extras/macFUSE ${MACFUSE_VERSION}.pkg" -target / >/dev/null

  if ! have_macos_fuse_provider; then
    fail "macFUSE installation completed, but libfuse.2.dylib was not found"
  fi
  prepare_macos_mountpoint
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
