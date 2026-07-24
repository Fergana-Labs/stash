"""Tests for `_install_gemini` — hooks merge into ~/.gemini/settings.json.

Gemini keeps its hooks inside the shared settings.json rather than a
dedicated hooks file, so the installer must preserve every unrelated
settings key and any user-added hooks while wiring the stash entries.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.main import _install_gemini


def _run_install(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    _install_gemini(False)
    return tmp_path / ".gemini"


def test_fresh_install_writes_settings_and_context(monkeypatch, tmp_path: Path) -> None:
    gemini_dir = _run_install(monkeypatch, tmp_path)

    settings = json.loads((gemini_dir / "settings.json").read_text())
    events = set(settings["hooks"])
    assert {"SessionStart", "BeforeAgent", "AfterTool", "AfterAgent", "SessionEnd"} <= events
    commands = json.dumps(settings)
    # Machine-independent commands: the CLI runs its own shipped scripts, so
    # no absolute install path may leak into the user's settings.json.
    assert "stash hook run gemini" in commands
    assert "stashai/plugin/assets/gemini" not in commands
    assert "${PLUGIN_ROOT}" not in commands

    assert "stash" in (gemini_dir / "GEMINI.md").read_text()


def test_install_preserves_existing_settings_and_user_hooks(monkeypatch, tmp_path: Path) -> None:
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True)
    user_hook = {"matcher": "*", "hooks": [{"type": "command", "command": "echo mine"}]}
    (gemini_dir / "settings.json").write_text(
        json.dumps({"theme": "dark", "hooks": {"SessionStart": [user_hook]}})
    )

    _run_install(monkeypatch, tmp_path)

    settings = json.loads((gemini_dir / "settings.json").read_text())
    assert settings["theme"] == "dark"
    session_start = settings["hooks"]["SessionStart"]
    assert user_hook in session_start
    assert any("stash hook run gemini" in json.dumps(e) for e in session_start)


def test_install_sweeps_stale_absolute_path_entries(monkeypatch, tmp_path: Path) -> None:
    """Pre-`stash hook run` installs embedded the install dir's absolute path;
    reinstalling must replace those with the stable command, not stack a
    second stash entry per event."""
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True)
    stale = {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "name": "stash-session-start",
                "command": "bash /old/venv/stashai/plugin/assets/gemini/scripts/_run.sh on_session_start",
            }
        ],
    }
    (gemini_dir / "settings.json").write_text(json.dumps({"hooks": {"SessionStart": [stale]}}))

    _run_install(monkeypatch, tmp_path)

    session_start = json.loads((gemini_dir / "settings.json").read_text())["hooks"]["SessionStart"]
    stash_entries = [e for e in session_start if "stash" in json.dumps(e)]
    assert len(stash_entries) == 1
    assert "stash hook run gemini on_session_start" in json.dumps(stash_entries[0])


def test_second_run_is_noop(monkeypatch, tmp_path: Path) -> None:
    gemini_dir = _run_install(monkeypatch, tmp_path)
    before = (gemini_dir / "settings.json").read_text()

    status, _ = _install_gemini(False)

    assert status == "skipped"
    assert (gemini_dir / "settings.json").read_text() == before
