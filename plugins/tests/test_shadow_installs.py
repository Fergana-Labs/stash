"""The shadow-install warning exists because a bare pip install leaves a
second, never-updating `stash` on PATH that wins in some contexts (pyenv
shims prepend their bin dir) — hooks then run stale code long after the
install that caused it. These tests pin the triggering conditions."""

import os
from pathlib import Path

import pytest

from stashai.plugin.doctor import find_stash_installs, shadow_install_warning


def _make_stash(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / "stash"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    return exe


def test_single_install_is_quiet(tmp_path, monkeypatch):
    _make_stash(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    assert shadow_install_warning() is None


def test_symlinked_duplicate_counts_as_one_install(tmp_path, monkeypatch):
    # uv setups expose the same binary twice (~/.local/bin symlink + the tool
    # venv's bin). That is one install, not a shadow.
    real = _make_stash(tmp_path / "venv" / "bin")
    link_dir = tmp_path / "local"
    link_dir.mkdir()
    (link_dir / "stash").symlink_to(real)
    monkeypatch.setenv("PATH", f"{link_dir}{os.pathsep}{real.parent}")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    assert len(find_stash_installs()) == 1
    assert shadow_install_warning() is None


def test_two_distinct_installs_warn_with_both_paths(tmp_path, monkeypatch):
    first = _make_stash(tmp_path / "local" / "bin")
    stale = _make_stash(tmp_path / "pyenv" / "shims")
    monkeypatch.setenv("PATH", f"{first.parent}{os.pathsep}{stale.parent}")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    warning = shadow_install_warning()
    assert warning is not None
    assert str(first) in warning
    assert str(stale) in warning


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_unreadable_path_entry_is_skipped(tmp_path, monkeypatch):
    # WSL appends the Windows PATH to $PATH, and some of those directories
    # (e.g. /mnt/c/WINDOWS/system32/config/systemprofile/.../WindowsApps)
    # raise PermissionError on stat(). That escaped find_stash_installs() and
    # crashed every SessionStart hook before it could emit its context — a
    # silent failure, since the session record is created earlier.
    denied = tmp_path / "denied"
    denied.mkdir()
    denied.chmod(0o000)
    real = _make_stash(tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{denied}{os.pathsep}{real.parent}")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    try:
        assert find_stash_installs() == [real]
        assert shadow_install_warning() is None
    finally:
        denied.chmod(0o755)  # let tmp_path cleanup remove it


def test_activated_dev_venv_suppresses_warning(tmp_path, monkeypatch):
    # Dev mode (`source .venv/bin/activate`) intentionally puts a second
    # stash on PATH; warning would otherwise fire on every dev session.
    venv_stash = _make_stash(tmp_path / ".venv" / "bin")
    release = _make_stash(tmp_path / "local" / "bin")
    monkeypatch.setenv("PATH", f"{venv_stash.parent}{os.pathsep}{release.parent}")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / ".venv"))
    assert shadow_install_warning() is None
