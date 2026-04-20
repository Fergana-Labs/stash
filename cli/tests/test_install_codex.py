"""Tests for `_install_codex` — focused on the config.toml append behavior."""

from __future__ import annotations

import tomllib
from pathlib import Path

from cli.main import _install_codex


def _run_install(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    _install_codex(False)
    return tmp_path / ".codex" / "config.toml"


def test_fresh_install_writes_profile_block(monkeypatch, tmp_path: Path) -> None:
    cfg = _run_install(monkeypatch, tmp_path)
    body = cfg.read_text()
    assert "[profiles.stash]" in body
    assert "[sandbox_workspace_write]" in body
    # TOML must still parse cleanly after our append.
    with cfg.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["profiles"]["stash"]["approval_policy"] == "on-failure"
    assert parsed["profiles"]["stash"]["sandbox_mode"] == "workspace-write"
    assert parsed["profiles"]["stash"]["sandbox_workspace_write"]["network_access"] is True
    # Top-level network grant — what lets plain `codex` stream without --profile.
    assert parsed["sandbox_workspace_write"]["network_access"] is True


def test_second_run_is_noop(monkeypatch, tmp_path: Path) -> None:
    cfg = _run_install(monkeypatch, tmp_path)
    before = cfg.read_text()
    _install_codex(False)
    assert cfg.read_text() == before


def test_install_preserves_unrelated_user_config(monkeypatch, tmp_path: Path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    cfg = codex_dir / "config.toml"
    cfg.write_text('[model]\nname = "something-custom"\n')

    cfg = _run_install(monkeypatch, tmp_path)
    body = cfg.read_text()

    assert 'name = "something-custom"' in body
    assert "[profiles.stash]" in body
    with cfg.open("rb") as f:
        tomllib.load(f)
