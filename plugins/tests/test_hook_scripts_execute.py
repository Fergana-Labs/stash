"""Execute every `stash hook run` script end-to-end against its fixture.

`stash hook run <agent> <event>` runs these exact files via runpy, so these
tests cover the same lines the dispatcher runs — an arity or import regression
in any script (like the historical `uploads_enabled(cfg, event)` TypeError
that broke every Codex session start) fails loudly here instead of in the
field.
"""

from __future__ import annotations

import io
import json
import runpy
import sys
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Mirrors _HOOK_EVENTS in cli/main.py; test_hook_cli.py asserts the CLI table
# matches the script files these entries point at.
_AGENT_EVENTS = {
    "claude": ("on_session_start", "on_prompt", "on_tool_use", "on_stop", "on_session_end"),
    "codex": ("on_session_start", "on_prompt", "on_tool_use", "on_stop"),
    "cursor": (
        "on_session_start",
        "on_prompt",
        "on_tool_use",
        "on_agent_response",
        "on_session_end",
    ),
    "gemini": ("on_session_start", "on_prompt", "on_tool_use", "on_stop", "on_session_end"),
    "hermes": ("on_session_start", "on_prompt", "on_tool_use", "on_stop", "on_session_end"),
    "openclaw": ("on_session_start", "on_prompt", "on_stop", "on_session_end"),
    "opencode": ("on_session_start", "on_prompt", "on_tool_use", "on_session_end"),
}

# Each agent's DATA_DIR env var (see each plugin's scripts/config.py).
_DATA_DIR_ENV = {
    "claude": "CLAUDE_PLUGIN_DATA",
    "codex": "STASH_CODEX_DATA",
    "cursor": "STASH_CURSOR_DATA",
    "gemini": "STASH_GEMINI_DATA",
    "hermes": "STASH_HERMES_DATA",
    "openclaw": "STASH_OPENCLAW_DATA",
    "opencode": "STASH_OPENCODE_DATA",
}

_CASES = [(agent, event) for agent, events in _AGENT_EVENTS.items() for event in events]


@pytest.mark.parametrize(("agent", "event"), _CASES)
def test_hook_script_executes(agent, event, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv(_DATA_DIR_ENV[agent], str(tmp_path / "hook-data"))
    fixture = (FIXTURES / agent / f"{event.removeprefix('on_')}.json").read_text()
    monkeypatch.setattr(sys, "stdin", io.StringIO(fixture))
    scripts_dir = PLUGINS_DIR / f"{agent}-plugin" / "scripts"
    monkeypatch.syspath_prepend(str(scripts_dir))

    # The scripts import flat sibling modules (`adapt`, `config`); drop any
    # cached copy so each run binds this plugin's modules and this test's env.
    for mod in ("adapt", "config"):
        sys.modules.pop(mod, None)
    try:
        runpy.run_path(str(scripts_dir / f"{event}.py"), run_name="__main__")
    finally:
        for mod in ("adapt", "config"):
            sys.modules.pop(mod, None)


def test_codex_hooks_json_template_shape() -> None:
    """Codex rejects the whole hooks file when it sees unknown top-level keys,
    and trusts hooks by command hash — commands must be machine-independent."""
    data = json.loads((PLUGINS_DIR / "codex-plugin" / "hooks.json").read_text())
    assert set(data.keys()) == {"hooks"}
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert hook["command"].startswith("stash hook run codex ")


def test_claude_hooks_json_commands_are_machine_independent() -> None:
    data = json.loads((PLUGINS_DIR / "claude-plugin" / "hooks" / "hooks.json").read_text())
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert hook["command"].startswith("stash hook run claude ")


def test_gemini_settings_snippet_commands_are_machine_independent() -> None:
    data = json.loads((PLUGINS_DIR / "gemini-plugin" / "settings.snippet.json").read_text())
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert hook["command"].startswith("stash hook run gemini ")


def test_cursor_hooks_json_commands_are_machine_independent() -> None:
    data = json.loads((PLUGINS_DIR / "cursor-plugin" / "hooks.json").read_text())
    for entries in data["hooks"].values():
        for entry in entries:
            assert entry["command"].startswith("stash hook run cursor ")


def test_hermes_config_snippet_commands_are_machine_independent() -> None:
    text = (PLUGINS_DIR / "hermes-plugin" / "config.snippet.yaml").read_text()
    assert "stash hook run hermes " in text
    assert "${PLUGIN_ROOT}" not in text
