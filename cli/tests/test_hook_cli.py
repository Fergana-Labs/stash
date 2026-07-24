"""Tests for `stash hook` — the stable dispatcher Codex hook commands call."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app

FIXTURES = Path(__file__).resolve().parent.parent.parent / "plugins" / "tests" / "fixtures"

runner = CliRunner()


def test_hook_run_rejects_unknown_agent() -> None:
    result = runner.invoke(app, ["hook", "run", "bogus", "on_stop"])
    assert result.exit_code == 1


def test_hook_run_rejects_unknown_event() -> None:
    result = runner.invoke(app, ["hook", "run", "codex", "bogus"])
    assert result.exit_code == 1


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
