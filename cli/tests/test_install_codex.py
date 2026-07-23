"""Tests for `_install_codex` — config.toml append behavior and the
hooks.json stable-command invariant."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from cli.main import _install_codex

_CODEX_EVENTS = ("on_session_start", "on_prompt", "on_tool_use", "on_stop")


def _run_install(monkeypatch, tmp_path: Path, allow_network: bool = True) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr("cli.main._ask_codex_network_access", lambda: allow_network)
    _install_codex(False)
    return tmp_path / ".codex" / "config.toml"


def test_fresh_install_writes_profile_block(monkeypatch, tmp_path: Path) -> None:
    cfg = _run_install(monkeypatch, tmp_path)
    body = cfg.read_text()
    assert "[profiles.stash]" in body
    assert "[sandbox_workspace_write]" in body
    assert "hooks = true" in body
    assert "codex_hooks" not in body
    # TOML must still parse cleanly after our append.
    with cfg.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["features"]["hooks"] is True
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


def test_preexisting_features_section_no_duplicate(monkeypatch, tmp_path: Path) -> None:
    """If the user already has [features], the installer must merge into it
    rather than appending a duplicate header (which breaks TOML parsing)."""
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    cfg = codex_dir / "config.toml"
    cfg.write_text("[features]\nsuppress_unstable_features_warning = true\n")

    cfg = _run_install(monkeypatch, tmp_path)
    body = cfg.read_text()

    assert body.count("[features]") == 1
    with cfg.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["features"]["hooks"] is True
    assert parsed["features"]["suppress_unstable_features_warning"] is True


def _hook_commands(hooks_path: Path) -> list[str]:
    data = json.loads(hooks_path.read_text())
    commands = []
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                commands.append(hook["command"])
    return commands


def test_fresh_install_writes_stable_hooks_json(monkeypatch, tmp_path: Path) -> None:
    """Codex trusts hooks by command hash: commands must be machine-independent
    (no absolute paths) so trust survives stash/python upgrades."""
    _run_install(monkeypatch, tmp_path)
    hooks_path = tmp_path / ".codex" / "hooks.json"
    data = json.loads(hooks_path.read_text())

    # Codex rejects the whole file on unknown top-level keys.
    assert set(data.keys()) == {"hooks"}
    commands = _hook_commands(hooks_path)
    assert sorted(commands) == sorted(f"stash hook run codex {e}" for e in _CODEX_EVENTS)
    assert all("/" not in c for c in commands)


def test_hooks_json_migration(monkeypatch, tmp_path: Path) -> None:
    """Old installs left a `_comment` key (Codex rejects the file for it) and
    absolute-path entries (trust breaks on upgrade). Reinstall must sweep both
    while preserving user-added hooks."""
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    hooks_path = codex_dir / "hooks.json"
    old_entry = {
        "hooks": [
            {
                "type": "command",
                "command": (
                    "bash /old/venv/lib/python3.11/site-packages/stashai/plugin/"
                    "assets/codex/scripts/_run.sh on_session_start"
                ),
                "timeout": 5,
            }
        ]
    }
    user_entry = {"hooks": [{"type": "command", "command": "echo user-hook", "timeout": 1}]}
    hooks_path.write_text(
        json.dumps(
            {
                "_comment": "stale comment Codex chokes on",
                "hooks": {"SessionStart": [old_entry, user_entry]},
            }
        )
    )

    _run_install(monkeypatch, tmp_path)
    data = json.loads(hooks_path.read_text())

    assert set(data.keys()) == {"hooks"}
    session_start = data["hooks"]["SessionStart"]
    assert user_entry in session_start
    commands = [h["command"] for e in session_start for h in e["hooks"]]
    assert "stash hook run codex on_session_start" in commands
    assert not any("_run.sh" in c for c in commands)


def test_reinstall_hooks_json_byte_stable(monkeypatch, tmp_path: Path) -> None:
    """The trust-survival invariant: reinstalling must never rewrite the hook
    definitions, or Codex silently distrusts them."""
    _run_install(monkeypatch, tmp_path)
    hooks_path = tmp_path / ".codex" / "hooks.json"
    before = hooks_path.read_bytes()
    _install_codex(False)
    assert hooks_path.read_bytes() == before


def test_preexisting_unmarked_skill_sections_do_not_duplicate(monkeypatch, tmp_path: Path) -> None:
    """Older/manual installs may already contain the Stash sections without
    the current marker. Reinstalling must not append duplicate TOML tables."""
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    cfg = codex_dir / "config.toml"
    cfg.write_text(
        "\n".join(
            [
                "[features]",
                "suppress_unstable_features_warning = true",
                "hooks = true",
                "",
                "[sandbox_workspace_write]",
                "network_access = true",
                "",
                "[profiles.stash]",
                'approval_policy = "on-failure"',
                'sandbox_mode = "workspace-write"',
                "",
                "[profiles.stash.sandbox_workspace_write]",
                "network_access = true",
                "",
            ]
        )
    )

    cfg = _run_install(monkeypatch, tmp_path)
    body = cfg.read_text()

    assert body.count("[features]") == 1
    assert body.count("[sandbox_workspace_write]") == 1
    assert body.count("[profiles.stash]") == 1
    assert body.count("[profiles.stash.sandbox_workspace_write]") == 1
    with cfg.open("rb") as f:
        parsed = tomllib.load(f)
    assert parsed["features"]["hooks"] is True
    assert parsed["features"]["suppress_unstable_features_warning"] is True
