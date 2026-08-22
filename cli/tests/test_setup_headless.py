"""Headless `stash setup`: inside a coding agent session there is no TTY, so
setup must be fully drivable by flags — the agent asks the wizard's questions
in conversation, then runs one deterministic command. A missing decision must
fail loud naming the flag to pass, never abort with a bare TTY error (the
pre-flag behavior) and never silently assume a default."""

import sys

import pytest
import typer
from typer.testing import CliRunner

import cli.import_history as import_history_mod
from cli import main


class _Stdin:
    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture
def calls(monkeypatch):
    """Stub every side effect and record what setup decided to do."""
    calls = {
        "start_streaming": 0,
        "stop_streaming": 0,
        "saved_agents": None,
        "hooks_installed": None,
        "connected": 0,
        "import_spawned": None,
        "wizard_runs": 0,
    }
    monkeypatch.setattr(main, "_require_auth", lambda: {"api_key": "k"})
    monkeypatch.setattr(main.telemetry, "record", lambda *a, **kw: None)
    monkeypatch.setattr(main, "load_config", lambda: {"api_key": "k"})
    monkeypatch.setattr(main, "_detected_agents", lambda: ["claude", "codex"])
    monkeypatch.setattr(main, "start_streaming", lambda: calls.__setitem__("start_streaming", 1))
    monkeypatch.setattr(main, "stop_streaming", lambda: calls.__setitem__("stop_streaming", 1))
    monkeypatch.setattr(main, "save_enabled_agents", lambda a: calls.__setitem__("saved_agents", a))
    monkeypatch.setattr(
        main,
        "_install_all_hooks",
        lambda a, use_json=False: calls.__setitem__("hooks_installed", a),
    )
    monkeypatch.setattr(
        main,
        "_auto_connect_repo",
        lambda root, cfg, use_json=False: calls.__setitem__("connected", 1),
    )
    monkeypatch.setattr(
        main, "_spawn_history_import", lambda n: calls.__setitem__("import_spawned", n)
    )
    monkeypatch.setattr(main, "_run_setup_wizard", lambda: calls.__setitem__("wizard_runs", 1))
    monkeypatch.setattr(
        import_history_mod, "discover_conversations", lambda agents: ["c1", "c2", "c3"]
    )
    return calls


def _setup(record=None, agents=None, connect=None, import_history=None):
    main.setup_cmd(record=record, agents=agents, connect=connect, import_history=import_history)


def test_no_tty_without_flags_fails_naming_the_missing_flags(calls, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))

    with pytest.raises(typer.Exit):
        _setup()

    err = capsys.readouterr().err
    assert "--record/--no-record" in err
    assert "--connect/--no-connect" in err
    assert calls["wizard_runs"] == 0


def test_tty_without_flags_runs_the_interactive_wizard(calls, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=True))

    _setup()

    assert calls["wizard_runs"] == 1


def test_any_flag_forces_headless_even_on_a_tty(calls, monkeypatch):
    # An agent that passes flags wants determinism — never drop into prompts.
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=True))

    with pytest.raises(typer.Exit):
        _setup(record=False)

    assert calls["wizard_runs"] == 0


def test_full_flags_drive_every_setup_step(calls, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))

    _setup(record=True, agents="claude,codex", connect=True, import_history=True)

    assert calls["start_streaming"] == 1
    assert calls["saved_agents"] == ["claude", "codex"]
    assert calls["hooks_installed"] == ["claude", "codex"]
    assert calls["connected"] == 1
    assert calls["import_spawned"] == 3


def test_no_record_needs_no_agents_or_import_decision(calls, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))

    _setup(record=False, connect=False)

    assert calls["stop_streaming"] == 1
    assert calls["start_streaming"] == 0
    assert calls["connected"] == 0
    assert calls["import_spawned"] is None


def test_unknown_agent_fails_and_names_the_detected_ones(calls, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))

    with pytest.raises(typer.Exit):
        _setup(record=True, agents="cursor", connect=False, import_history=False)

    err = capsys.readouterr().err
    assert "cursor" in err
    assert "claude" in err
    assert calls["start_streaming"] == 0


def test_import_history_without_record_is_an_error(calls, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))

    with pytest.raises(typer.Exit):
        _setup(record=False, connect=False, import_history=True)

    assert "--record" in capsys.readouterr().err


def test_flags_parse_end_to_end_through_the_cli(calls):
    result = CliRunner().invoke(
        main.app,
        ["setup", "--record", "--agents", "claude", "--connect", "--import-history"],
    )

    assert result.exit_code == 0, result.output
    assert calls["saved_agents"] == ["claude"]
    assert calls["import_spawned"] == 3
