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
    # Pi's handlers are named like Claude's; its hook wrappers map pi's own event
    # names onto them (assistant_message -> on_stop), so the handler set is what
    # this table records.
    "pi": ("on_session_start", "on_prompt", "on_tool_use", "on_stop", "on_session_end"),
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
    "pi": "STASH_PI_DATA",
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

    # A guarded hook swallows its own crash so the host keeps its exit contract,
    # which makes a green runpy call meaningless on its own. The failure record is
    # the only witness that the handler actually ran to completion.
    status_file = tmp_path / "hook-data" / "upload_status.json"
    if status_file.exists():
        recorded = json.loads(status_file.read_text())
        assert recorded.get("last_failure_operation") != "hook_run", (
            f"{agent}/{event} crashed inside its guard: {recorded}"
        )


def test_pi_fatal_handler_records_then_honours_exit_zero(monkeypatch, tmp_path: Path) -> None:
    """Break a real pi handler on purpose and check what the payload's failure
    contract promises: the crash is written into the ``upload_status.json`` that
    ``stash status`` reads, it is announced on stdout (pi's only channel to the
    user), and the hook still returns normally so pi keeps seeing exit 0 — pi
    discards a hook that fails, so a non-zero tail would silently stop every
    recording for that install. Drop the ``guard_hook_main`` call from
    ``on_session_start.py`` and all three assertions go red; make the guard
    re-raise and the exit-0 half goes red.
    """
    scripts_dir = PLUGINS_DIR / "pi-plugin" / "scripts"
    data_dir = tmp_path / "hook-data"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("STASH_PI_DATA", str(data_dir))
    monkeypatch.syspath_prepend(str(scripts_dir))
    # A configured machine, or the handler returns early on the "not set up"
    # branch and never reaches the crash. `enabled_agents` must name pi
    # explicitly: hooks.py binds _CONFIG_FILE at import time, so without the
    # rebind below the developer's own ~/.stash/config.json answers the gate
    # (measured: a machine whose list is ["claude", "codex", "opencode"] silently
    # disabled pi and the handler exited before the exploding call).
    (tmp_path / ".stash").mkdir()
    user_config = tmp_path / ".stash" / "config.json"
    user_config.write_text(
        json.dumps(
            {
                "api_key": "key",
                "username": "alice",
                "base_url": "https://api.invalid",
                "enabled_agents": ["pi"],
            }
        )
    )
    monkeypatch.setattr("stashai.plugin.hooks._CONFIG_FILE", user_config)
    for mod in ("adapt", "config"):
        sys.modules.pop(mod, None)

    def exploding_create_session_record(client, cfg, state, event, target_dir):
        raise RuntimeError("handler died mid-event")

    monkeypatch.setattr(
        "stashai.plugin.hooks.create_session_record", exploding_create_session_record
    )
    monkeypatch.setattr(
        sys, "stdin", io.StringIO((FIXTURES / "pi" / "session_start.json").read_text())
    )
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    runpy.run_path(str(scripts_dir / "on_session_start.py"), run_name="__main__")

    recorded = json.loads((data_dir / "upload_status.json").read_text())
    assert recorded["last_failure_operation"] == "hook_run"
    assert "handler died mid-event" in recorded["last_error"]
    assert "systemMessage" in stdout.getvalue()
    assert "stash status" in stdout.getvalue()
    assert "handler died mid-event" in stderr.getvalue(), "the traceback must not be swallowed"


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
    """No absolute paths: hooks.json ships to every machine as-is.

    SessionStart additionally runs the plugin-owned CLI floor check first (see
    test_ensure_cli.py) — the only upgrade path a too-old CLI can still reach —
    so it is prefixed with a ${CLAUDE_PLUGIN_ROOT} invocation instead of
    starting at `stash`. That variable is expanded by Claude Code, so the
    command stays machine-independent.
    """
    data = json.loads((PLUGINS_DIR / "claude-plugin" / "hooks" / "hooks.json").read_text())
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                command = hook["command"]
                assert "stash hook run claude " in command
                assert not command.startswith("/")
                assert "/Users/" not in command and "/home/" not in command
                if "ensure_cli.sh" in command:
                    assert command.startswith("bash ${CLAUDE_PLUGIN_ROOT}/scripts/")


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
