"""Adapter round-trip tests across all plugins.

For each plugin's adapt.py, load the fixture payload and assert the resulting
HookEvent matches the expected canonical shape. Catches regressions when
upstream agents change their stdin JSON.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parent.parent
SHARED = PLUGINS_DIR / "shared"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SHARED))


def _load_adapt(plugin: str):
    """Load <plugin>-plugin/scripts/adapt.py fresh for each test."""
    path = PLUGINS_DIR / f"{plugin}-plugin" / "scripts" / "adapt.py"
    spec = importlib.util.spec_from_file_location(f"adapt_{plugin}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_fixture(plugin: str, name: str) -> dict:
    return json.loads((FIXTURES / plugin / f"{name}.json").read_text())


PLUGINS = ["claude", "cursor", "gemini", "codex", "opencode", "openclaw"]


@pytest.mark.parametrize("plugin", PLUGINS)
def test_session_start(plugin):
    adapt = _load_adapt(plugin)
    event = adapt.adapt_session_start(_load_fixture(plugin, "session_start"))
    assert event.kind == "session_start"
    assert event.session_id  # non-empty


@pytest.mark.parametrize("plugin", PLUGINS)
def test_prompt(plugin):
    adapt = _load_adapt(plugin)
    event = adapt.adapt_prompt(_load_fixture(plugin, "prompt"))
    assert event.kind == "prompt"
    assert event.session_id
    assert event.prompt_text  # non-empty


@pytest.mark.parametrize("plugin", PLUGINS)
def test_tool_use(plugin):
    adapt = _load_adapt(plugin)
    event = adapt.adapt_tool_use(_load_fixture(plugin, "tool_use"))
    assert event.kind == "tool_use"
    assert event.session_id
    assert event.tool_name  # non-empty normalized name
    # Tool names should be lowercase canonical names
    assert event.tool_name == event.tool_name.lower()
    assert isinstance(event.tool_input, dict)


@pytest.mark.parametrize("plugin", PLUGINS)
def test_stop(plugin):
    adapt = _load_adapt(plugin)
    event = adapt.adapt_stop(_load_fixture(plugin, "stop"))
    assert event.kind == "stop"
    assert event.session_id
    assert event.last_assistant_message  # non-empty


def test_codex_notify_fallback():
    adapt = _load_adapt("codex")
    event = adapt.adapt_notify(_load_fixture("codex", "notify"))
    assert event.kind == "stop"
    assert event.last_assistant_message == "Turn complete."


def test_tool_name_normalization():
    """Each plugin's adapter should normalize its agent-native tool names."""
    cases = [
        ("claude", "Edit", "edit"),
        ("claude", "Bash", "bash"),
        ("cursor", "edit_file", "edit"),
        ("cursor", "run_terminal_cmd", "bash"),
        ("gemini", "run_shell_command", "bash"),
        ("gemini", "read_file", "read"),
        ("codex", "Bash", "bash"),
        ("codex", "apply_patch", "edit"),
        ("opencode", "edit", "edit"),
        ("openclaw", "file.edit", "edit"),
        ("openclaw", "shell.run", "bash"),
    ]
    for plugin, raw, expected in cases:
        adapt = _load_adapt(plugin)
        event = adapt.adapt_tool_use({"tool_name": raw, "session_id": "x"})
        assert event.tool_name == expected, (
            f"{plugin}: {raw!r} -> {event.tool_name!r}, expected {expected!r}"
        )
