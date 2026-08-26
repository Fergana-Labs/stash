"""Applying web-onboarding choices at signin: a user who answered the setup
questions on the web must not be quizzed again in the terminal. Every stored
choice is applied and printed as one line — transparent, not interactive.
The single exception is the folder question, which a browser cannot answer.
Once applied, the choices are marked consumed so a later standalone signin
runs the wizard instead of re-applying them.
"""

from pathlib import Path

import pytest
import typer

from cli import main


def _prefs(**overrides) -> dict:
    prefs = {
        "enabled_agents": ["claude", "cursor"],
        "record_scope": "everything",
        "import_history": True,
        "claude_md_opt_in": True,
        "consumed_at": None,
    }
    prefs.update(overrides)
    return prefs


class _FakeClient:
    def __init__(self, calls: dict):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def consume_onboarding_preferences(self) -> dict:
        self._calls["consumed"] += 1
        return {"ok": True}


@pytest.fixture
def calls(monkeypatch):
    """Stub every side effect and record what applying decided to do."""
    calls = {
        "recorded_paths": None,
        "saved_agents": None,
        "hooks_installed": None,
        "start_streaming": 0,
        "connected": 0,
        "import_spawned": None,
        "folder_picker_runs": 0,
        "consumed": 0,
    }
    monkeypatch.setattr(main, "_detected_agents", lambda: ["claude", "codex"])
    monkeypatch.setattr(
        main, "save_recorded_paths", lambda p: calls.__setitem__("recorded_paths", p)
    )
    monkeypatch.setattr(main, "save_enabled_agents", lambda a: calls.__setitem__("saved_agents", a))
    monkeypatch.setattr(
        main, "_install_all_hooks", lambda a: calls.__setitem__("hooks_installed", a)
    )
    monkeypatch.setattr(main, "start_streaming", lambda: calls.__setitem__("start_streaming", 1))
    monkeypatch.setattr(
        main, "_auto_connect_repo", lambda root, cfg: calls.__setitem__("connected", 1)
    )
    monkeypatch.setattr(main, "_conversations_to_import", lambda agents: ["c1", "c2", "c3"])
    monkeypatch.setattr(
        main, "_spawn_history_import", lambda n: calls.__setitem__("import_spawned", n)
    )
    monkeypatch.setattr(main, "_client", lambda auto=False: _FakeClient(calls))
    monkeypatch.setattr(main, "_show_setup_complete_splash", lambda: None)

    def _fake_picker(start: Path) -> Path:
        calls["folder_picker_runs"] += 1
        return Path("/tmp/picked")

    monkeypatch.setattr(main, "_pick_record_folder", _fake_picker)
    return calls


def test_applies_every_choice_without_asking(calls, capsys):
    main._apply_web_onboarding(_prefs(), {"api_key": "k"})

    assert calls["recorded_paths"] == []
    assert calls["start_streaming"] == 1
    # Cursor was chosen on the web but isn't installed here — only the
    # intersection with detected agents is enabled, and the skip is printed.
    assert calls["saved_agents"] == ["claude"]
    assert calls["hooks_installed"] == ["claude"]
    assert calls["connected"] == 1
    assert calls["import_spawned"] == 3
    assert calls["consumed"] == 1
    assert calls["folder_picker_runs"] == 0

    out = capsys.readouterr().out
    assert "Recording Claude Code" in out
    assert "Cursor isn't on this machine" in out
    assert "everywhere on this machine" in out


def test_selected_folders_asks_the_one_local_question(calls):
    main._apply_web_onboarding(_prefs(record_scope="selected_folders"), {"api_key": "k"})

    assert calls["folder_picker_runs"] == 1
    assert calls["recorded_paths"] == ["/tmp/picked"]
    assert calls["consumed"] == 1


def test_cancelled_folder_picker_leaves_choices_unconsumed(calls, monkeypatch):
    """Ctrl-C in the picker must abort before anything is applied or consumed,
    so the next signin starts over from the stored choices."""
    monkeypatch.setattr(main, "_pick_record_folder", lambda start: None)

    with pytest.raises(typer.Exit):
        main._apply_web_onboarding(_prefs(record_scope="selected_folders"), {"api_key": "k"})

    assert calls["recorded_paths"] is None
    assert calls["consumed"] == 0


def test_opt_outs_are_respected_and_printed(calls, capsys):
    main._apply_web_onboarding(
        _prefs(import_history=False, claude_md_opt_in=False), {"api_key": "k"}
    )

    assert calls["connected"] == 0
    assert calls["import_spawned"] is None
    assert calls["consumed"] == 1

    out = capsys.readouterr().out
    assert "Leaving CLAUDE.md untouched" in out
    assert "Skipping history import" in out


def test_no_chosen_agent_installed_warns_instead_of_recording(calls, capsys):
    # The fixture detects claude and codex; the user chose only gemini.
    main._apply_web_onboarding(_prefs(enabled_agents=["gemini"]), {"api_key": "k"})

    assert calls["saved_agents"] == []
    assert calls["hooks_installed"] == []
    out = capsys.readouterr().out
    assert "None of the agents you picked are installed here" in out
