"""Tests for `_install_codex` — focused on the config.toml append behavior.

The risk this test guards against: an existing user has the old stash-plugin
block (features only) in ~/.codex/config.toml. On the next `stash connect`
they should get the new `[profiles.stash]` block appended so `codex --profile
stash` works, without duplicating the whole snippet.
"""

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


def test_upgrade_from_old_install_appends_missing_blocks(monkeypatch, tmp_path: Path) -> None:
    # Simulate a user who installed before the profile + sandbox blocks existed.
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    cfg = codex_dir / "config.toml"
    cfg.write_text(
        "# stash-plugin\n"
        "[features]\n"
        "codex_hooks = true\n"
        "suppress_unstable_features_warning = true\n"
    )

    cfg = _run_install(monkeypatch, tmp_path)
    body = cfg.read_text()

    # Features block preserved (not duplicated); both new blocks appended.
    assert body.count("[features]") == 1
    assert "[profiles.stash]" in body
    assert "[sandbox_workspace_write]" in body
    with cfg.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["sandbox_workspace_write"]["network_access"] is True
    assert parsed["profiles"]["stash"]["sandbox_workspace_write"]["network_access"] is True

    # Second run is a no-op.
    before = cfg.read_text()
    _install_codex(False)
    assert cfg.read_text() == before


def test_upgrade_appends_only_missing_block(monkeypatch, tmp_path: Path) -> None:
    # Simulate a user who already has the profile block (older upgrade path)
    # but is missing the newer top-level sandbox block.
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    cfg = codex_dir / "config.toml"
    cfg.write_text(
        "# stash-plugin\n"
        "[features]\n"
        "codex_hooks = true\n"
        "\n"
        "[profiles.stash]\n"
        'approval_policy = "on-failure"\n'
        'sandbox_mode = "workspace-write"\n'
        "\n"
        "[profiles.stash.sandbox_workspace_write]\n"
        "network_access = true\n"
    )

    cfg = _run_install(monkeypatch, tmp_path)
    body = cfg.read_text()

    # Exactly one of each header — no duplicate profile.
    assert body.count("[profiles.stash]") == 1
    assert body.count("[sandbox_workspace_write]") == 1
    with cfg.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["sandbox_workspace_write"]["network_access"] is True


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
