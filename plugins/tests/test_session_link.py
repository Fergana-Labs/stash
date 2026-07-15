"""The session-record-link instruction is opt-in and independent of uploads.

`stash settings` writes `session_link` to ~/.stash/config.json, the Claude
plugin reads it, and SessionStart injects the "always include this link"
instruction only when it is on. Uploads (session record + watcher) must run
either way — turning the link off must not turn streaming off.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from cli import config as cli_config

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/claude-plugin/scripts"

_SCRIPT_MODULES = ("adapt", "config", "on_session_start")


@pytest.fixture
def plugin_home(tmp_path, monkeypatch):
    """A fake HOME whose ~/.stash/config.json both the CLI and plugin read."""
    home = tmp_path / "home"
    (home / ".stash").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(home / "plugin-data"))
    monkeypatch.delenv("CLAUDE_PLUGIN_USER_CONFIG_api_key", raising=False)
    monkeypatch.setattr(cli_config, "USER_CONFIG_FILE", home / ".stash" / "config.json")
    return home


@pytest.fixture
def session_start(plugin_home, monkeypatch):
    """Import the hook script fresh under the fake HOME."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    for name in _SCRIPT_MODULES:
        sys.modules.pop(name, None)
    yield importlib.import_module("on_session_start")
    for name in _SCRIPT_MODULES:
        sys.modules.pop(name, None)


def _run_hook(mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "get_stdin_data", lambda: {"session_id": "s1", "cwd": "/repo"})
    monkeypatch.setattr(mod, "uploads_enabled", lambda cfg: True)
    monkeypatch.setattr(
        mod, "create_session_record", lambda *a, **k: "https://app.example/sessions/s1"
    )
    monkeypatch.setattr(mod, "shadow_install_warning", lambda: None)
    watchers = []
    monkeypatch.setattr(mod, "spawn_session_watcher", lambda **kw: watchers.append(kw))
    mod.main()
    output = json.loads(capsys.readouterr().out)
    return output["hookSpecificOutput"]["additionalContext"], watchers


def test_link_instruction_off_by_default(plugin_home, session_start, monkeypatch, capsys):
    cli_config.save_config(api_key="k", username="alice")

    context, watchers = _run_hook(session_start, monkeypatch, capsys)

    assert "Session record" not in context
    # The toggle only silences the link — the session still streams.
    assert len(watchers) == 1


def test_link_instruction_injected_when_enabled(plugin_home, session_start, monkeypatch, capsys):
    cli_config.save_config(api_key="k", username="alice")
    cli_config.set_session_link(True)

    context, watchers = _run_hook(session_start, monkeypatch, capsys)

    assert "Session record: https://app.example/sessions/s1" in context
    assert len(watchers) == 1


def test_cli_toggle_and_plugin_config_agree(plugin_home, session_start):
    """CLI writer and plugin reader live in separate packages; pin the contract."""
    plugin_config = sys.modules["config"]

    assert cli_config.session_link_enabled() is False
    assert plugin_config.get_config()["session_link"] is False

    cli_config.set_session_link(True)
    assert cli_config.session_link_enabled() is True
    assert plugin_config.get_config()["session_link"] is True

    cli_config.set_session_link(False)
    assert plugin_config.get_config()["session_link"] is False
