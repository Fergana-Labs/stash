"""Tests for `stash hook` — the stable dispatcher agent hook commands call."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.main import _HOOK_EVENTS, app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "plugins" / "tests" / "fixtures"

runner = CliRunner()


def test_hook_run_rejects_unknown_agent() -> None:
    result = runner.invoke(app, ["hook", "run", "bogus", "on_stop"])
    assert result.exit_code == 1


@pytest.mark.parametrize("agent", sorted(_HOOK_EVENTS))
def test_hook_run_rejects_unknown_event(agent: str) -> None:
    result = runner.invoke(app, ["hook", "run", agent, "bogus"])
    assert result.exit_code == 1


def test_hook_events_table_matches_script_files() -> None:
    """Every dispatchable (agent, event) must have a script in the shipped
    assets, and every script must be dispatchable — a drifting table means
    hooks that silently do nothing or scripts nobody can run."""
    for agent, events in _HOOK_EVENTS.items():
        scripts_dir = REPO_ROOT / "stashai" / "plugin" / "assets" / agent / "scripts"
        on_disk = {p.stem for p in scripts_dir.glob("on_*.py")}
        assert set(events) == on_disk, f"{agent}: table {sorted(events)} vs files {sorted(on_disk)}"


def test_hook_auto_update_writes_preference(monkeypatch, tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr("cli.config.USER_CONFIG_FILE", cfg_file)

    assert runner.invoke(app, ["hook", "auto-update", "on"]).exit_code == 0
    assert json.loads(cfg_file.read_text())["codex_auto_update"] is True

    assert runner.invoke(app, ["hook", "auto-update", "off"]).exit_code == 0
    assert json.loads(cfg_file.read_text())["codex_auto_update"] is False

    assert runner.invoke(app, ["hook", "auto-update", "maybe"]).exit_code == 1


def test_hook_run_codex_on_stop_executes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("STASH_CODEX_DATA", str(tmp_path / "codex-data"))
    # The hook scripts import flat sibling modules (`adapt`, `config`); drop
    # cached copies so this run binds the codex ones under this test's env.
    for mod in ("adapt", "config"):
        sys.modules.pop(mod, None)

    fixture = (FIXTURES / "codex" / "stop.json").read_text()
    try:
        result = runner.invoke(app, ["hook", "run", "codex", "on_stop"], input=fixture)
    finally:
        for mod in ("adapt", "config"):
            sys.modules.pop(mod, None)

    assert result.exit_code == 0
