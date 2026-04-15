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


PLUGINS = ["claude", "cursor", "gemini", "codex", "opencode"]


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


@pytest.mark.parametrize("plugin", ["claude", "gemini", "codex", "opencode"])
def test_stop(plugin):
    # Cursor intentionally has no stop hook — afterAgentResponse + sessionEnd
    # cover what used to be Cursor's `stop`. See cursor-plugin/hooks.json.
    adapt = _load_adapt(plugin)
    event = adapt.adapt_stop(_load_fixture(plugin, "stop"))
    assert event.kind == "stop"
    assert event.session_id
    assert event.last_assistant_message


def test_cursor_agent_response():
    adapt = _load_adapt("cursor")
    event = adapt.adapt_agent_response(_load_fixture("cursor", "agent_response"))
    assert event.kind == "stop"
    assert event.session_id
    assert event.last_assistant_message == "Done."


def test_cursor_tool_output_json_string_parses():
    """Cursor's tool_output is a JSON-stringified string. The adapter must
    parse it to a dict so summarize_tool_use doesn't crash on `.get()`."""
    adapt = _load_adapt("cursor")
    event = adapt.adapt_tool_use({
        "tool_name": "Shell",
        "session_id": "s1",
        "tool_input": {"command": "ls"},
        "tool_output": '{"stdout": "file.txt\\n", "exit_code": 0}',
    })
    assert isinstance(event.tool_response, dict)
    assert event.tool_response.get("stdout") == "file.txt\n"
    assert event.tool_response.get("exit_code") == 0

    # Non-JSON text falls back to {"raw": ...}.
    event2 = adapt.adapt_tool_use({
        "tool_name": "Shell",
        "session_id": "s1",
        "tool_input": {"command": "ls"},
        "tool_output": "not-json-text",
    })
    assert event2.tool_response == {"raw": "not-json-text"}


def test_codex_notify_fallback():
    adapt = _load_adapt("codex")
    event = adapt.adapt_notify(_load_fixture("codex", "notify"))
    assert event.kind == "stop"
    assert event.session_id == "cdx-1"  # comes from thread-id
    assert event.last_assistant_message == "Turn complete."


def test_push_event_stamps_client_into_metadata():
    """OctopusClient.push_event should merge the `client` facet into metadata."""
    from octopus_client import OctopusClient

    calls = []

    class FakeClient(OctopusClient):
        def _post(self, path, **kwargs):
            calls.append((path, kwargs))
            return {}

    c = FakeClient(base_url="http://x", api_key="k")

    c.push_event(
        workspace_id="ws1", agent_name="henry", event_type="tool_use",
        content="...", tool_name="edit", metadata={"cwd": "/tmp"}, client="cursor",
    )
    body = calls[-1][1]["json"]
    assert body["metadata"] == {"cwd": "/tmp", "client": "cursor"}

    c.push_event(
        workspace_id="ws1", agent_name="henry", event_type="user_message",
        content="hi", client="claude_code",
    )
    body = calls[-1][1]["json"]
    assert body["metadata"] == {"client": "claude_code"}

    c.push_event(
        workspace_id="ws1", agent_name="henry", event_type="user_message", content="hi",
    )
    body = calls[-1][1]["json"]
    assert "metadata" not in body


def test_tool_name_normalization():
    """Each plugin's adapter should normalize its agent-native tool names.

    Raw names come from each agent's actual wire format: Claude uses PascalCase
    (`Edit`, `Bash`), Cursor uses PascalCase (`Shell`, `Read`), Gemini uses
    snake_case (`run_shell_command`, `read_file`), Codex hardcodes `Bash` for
    every shell call, opencode uses lowercase (`edit`, `bash`).
    """
    cases = [
        ("claude", "Edit", "edit"),
        ("claude", "Bash", "bash"),
        ("cursor", "Shell", "bash"),
        ("cursor", "Read", "read"),
        ("cursor", "Grep", "grep"),
        ("gemini", "run_shell_command", "bash"),
        ("gemini", "read_file", "read"),
        ("gemini", "replace", "edit"),
        ("codex", "Bash", "bash"),
        ("opencode", "edit", "edit"),
        ("opencode", "bash", "bash"),
    ]
    for plugin, raw, expected in cases:
        adapt = _load_adapt(plugin)
        event = adapt.adapt_tool_use({"tool_name": raw, "session_id": "x"})
        assert event.tool_name == expected, (
            f"{plugin}: {raw!r} -> {event.tool_name!r}, expected {expected!r}"
        )


def test_client_facet_flows_through_stream_paths():
    """cfg['client'] must survive every stream_* helper and land as
    metadata.client on the wire."""
    from event import HookEvent
    from hooks import (
        stream_assistant_message, stream_session_end, stream_tool_use,
        stream_user_message,
    )
    from octopus_client import OctopusClient

    calls = []

    class FakeClient(OctopusClient):
        def _post(self, path, **kwargs):
            calls.append(kwargs.get("json", {}))
            return {}

    for client_name in ("cursor", "gemini_cli", "codex_cli", "opencode"):
        calls.clear()
        cfg = {
            "workspace_id": "ws1",
            "agent_name": "henry",
            "client": client_name,
        }
        state = {"session_id": "s1"}
        c = FakeClient(base_url="http://x", api_key="k")

        stream_user_message(c, cfg, state, "hello")
        stream_tool_use(c, cfg, state, HookEvent(
            kind="tool_use", tool_name="bash",
            tool_input={"command": "echo hi"}, tool_response={"stdout": "hi"},
        ))
        stream_assistant_message(c, cfg, state, HookEvent(
            kind="stop", last_assistant_message="done.",
        ))
        stream_session_end(c, cfg, state, HookEvent(kind="session_end"))

        for body in calls:
            assert body.get("metadata", {}).get("client") == client_name, (
                f"{client_name}: missing client facet in {body}"
            )


def test_stream_session_end_not_emitted_on_assistant_message():
    """stream_assistant_message must NOT emit a session_end event — that's
    the whole point of splitting it from stream_session_end."""
    from event import HookEvent
    from hooks import stream_assistant_message
    from octopus_client import OctopusClient

    calls = []

    class FakeClient(OctopusClient):
        def _post(self, path, **kwargs):
            calls.append(kwargs.get("json", {}))
            return {}

    c = FakeClient(base_url="http://x", api_key="k")
    cfg = {"workspace_id": "ws1", "agent_name": "henry", "client": "claude_code"}
    state = {"session_id": "s1"}
    stream_assistant_message(c, cfg, state, HookEvent(
        kind="stop", last_assistant_message="turn complete.",
    ))

    event_types = [b.get("event_type") for b in calls]
    assert "assistant_message" in event_types
    assert "session_end" not in event_types
