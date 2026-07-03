"""Adapter round-trip tests across all plugins.

For each plugin's adapt.py, load the fixture payload and assert the resulting
HookEvent matches the expected canonical shape. Catches regressions when
upstream agents change their stdin JSON.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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

# Openclaw's gateway has no tool-call visibility (tool_use comes from the
# delegated coding agent's own plugin), so its adapter intentionally omits
# adapt_tool_use.
_PLUGINS_WITH_TOOL_USE = [p for p in PLUGINS if p != "openclaw"]


@pytest.mark.parametrize("plugin", PLUGINS)
def test_session_start(plugin):
    adapt = _load_adapt(plugin)
    event = adapt.adapt_session_start(_load_fixture(plugin, "session_start"))
    assert event.kind == "session_start"
    assert event.session_id  # non-empty
    if plugin in ("codex", "cursor", "gemini"):
        assert event.transcript_path


# Cursor's beforeSubmitPrompt/postToolUse/afterAgentResponse payloads don't
# carry session_id (only conversation_id). Streaming reads state.session_id,
# saved at sessionStart, so the empty event.session_id is intentional.
_PLUGINS_WITH_PROMPT_SID = [p for p in PLUGINS if p != "cursor"]


@pytest.mark.parametrize("plugin", PLUGINS)
def test_prompt(plugin):
    adapt = _load_adapt(plugin)
    event = adapt.adapt_prompt(_load_fixture(plugin, "prompt"))
    assert event.kind == "prompt"
    if plugin in _PLUGINS_WITH_PROMPT_SID:
        assert event.session_id
    assert event.prompt_text  # non-empty
    assert event.cwd


@pytest.mark.parametrize("plugin", _PLUGINS_WITH_TOOL_USE)
def test_tool_use(plugin):
    adapt = _load_adapt(plugin)
    event = adapt.adapt_tool_use(_load_fixture(plugin, "tool_use"))
    assert event.kind == "tool_use"
    if plugin in _PLUGINS_WITH_PROMPT_SID:
        assert event.session_id
    assert event.tool_name  # non-empty normalized name
    # Tool names should be lowercase canonical names
    assert event.tool_name == event.tool_name.lower()
    assert isinstance(event.tool_input, dict)


@pytest.mark.parametrize("plugin", ["claude", "gemini", "codex", "opencode", "openclaw"])
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
    # afterAgentResponse has no session_id; streaming uses state.session_id.
    assert event.last_assistant_message == "Done."


def test_transcript_paths_flow_through_session_end_adapters():
    cases = [
        ("claude", {"session_id": "s1", "cwd": "/repo", "transcript_path": "/t/claude.jsonl"}),
        (
            "cursor",
            {
                "session_id": "s1",
                "workspace_roots": ["/repo"],
                "transcript_path": "/t/cursor.jsonl",
            },
        ),
        ("gemini", {"session_id": "s1", "cwd": "/repo", "transcript_path": "/t/gemini.json"}),
    ]
    for plugin, payload in cases:
        adapt = _load_adapt(plugin)
        event = adapt.adapt_session_end(payload)
        assert event.kind == "session_end"
        assert event.cwd == "/repo"
        assert event.transcript_path.startswith("/t/")


def test_cursor_tool_output_json_string_parses():
    """Cursor's tool_output is a JSON-stringified string. The adapter must
    parse it to a dict so summarize_tool_use doesn't crash on `.get()`."""
    adapt = _load_adapt("cursor")
    event = adapt.adapt_tool_use(
        {
            "tool_name": "Shell",
            "session_id": "s1",
            "tool_input": {"command": "ls"},
            "tool_output": '{"stdout": "file.txt\\n", "exit_code": 0}',
        }
    )
    assert isinstance(event.tool_response, dict)
    assert event.tool_response.get("stdout") == "file.txt\n"
    assert event.tool_response.get("exit_code") == 0

    # Non-JSON text falls back to {"raw": ...}.
    event2 = adapt.adapt_tool_use(
        {
            "tool_name": "Shell",
            "session_id": "s1",
            "tool_input": {"command": "ls"},
            "tool_output": "not-json-text",
        }
    )
    assert event2.tool_response == {"raw": "not-json-text"}


def test_model_extras_flow_from_agent_adapters():
    codex = _load_adapt("codex")
    for fixture_name in ("session_start", "prompt", "tool_use", "stop"):
        event = getattr(
            codex,
            {
                "session_start": "adapt_session_start",
                "prompt": "adapt_prompt",
                "tool_use": "adapt_tool_use",
                "stop": "adapt_stop",
            }[fixture_name],
        )(_load_fixture("codex", fixture_name))
        assert event.extras["model"] == "gpt-5-codex"
        assert event.extras["permission_mode"] == "default"

    cursor = _load_adapt("cursor")
    cursor_cases = [
        ("session_start", "adapt_session_start"),
        ("prompt", "adapt_prompt"),
        ("tool_use", "adapt_tool_use"),
        ("agent_response", "adapt_agent_response"),
        ("stop", "adapt_session_end"),
    ]
    for fixture_name, adapter_name in cursor_cases:
        event = getattr(cursor, adapter_name)(_load_fixture("cursor", fixture_name))
        assert event.extras["model"] == "claude-3.7-sonnet"
        assert event.extras["cursor_version"] == "1.7.0"
        assert event.extras["generation_id"].startswith("gen-")


def test_push_event_stamps_client_into_metadata():
    """StashClient.push_event should merge the `client` facet into metadata."""
    from stashai.plugin.stash_client import StashClient

    calls = []

    class FakeClient(StashClient):
        def _post(self, path, **kwargs):
            calls.append((path, kwargs))
            return {}

    c = FakeClient(base_url="http://x", api_key="k")

    c.push_event(
        agent_name="henry",
        event_type="tool_use",
        content="...",
        session_id="s1",
        tool_name="edit",
        metadata={"cwd": "/tmp"},
        client="cursor",
    )
    assert calls[-1][0] == "/api/v1/me/sessions/events"
    body = calls[-1][1]["json"]
    assert body["metadata"] == {"cwd": "/tmp", "client": "cursor"}

    c.push_event(
        agent_name="henry",
        event_type="user_message",
        content="hi",
        session_id="s1",
        client="claude_code",
    )
    body = calls[-1][1]["json"]
    assert body["metadata"] == {"client": "claude_code"}

    c.push_event(
        agent_name="henry",
        event_type="user_message",
        content="hi",
        session_id="s1",
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
        assert (
            event.tool_name == expected
        ), f"{plugin}: {raw!r} -> {event.tool_name!r}, expected {expected!r}"


def test_client_facet_flows_through_stream_paths():
    """cfg['client'] must survive every stream_* helper and land as
    metadata.client on the wire."""
    from stashai.plugin.event import HookEvent
    from stashai.plugin.hooks import (
        stream_assistant_message,
        stream_session_end,
        stream_tool_use,
        stream_user_message,
    )
    from stashai.plugin.stash_client import StashClient

    calls = []

    class FakeClient(StashClient):
        def _post(self, path, **kwargs):
            calls.append(kwargs.get("json", {}))
            return {}

    for client_name in ("cursor", "gemini_cli", "codex_cli", "opencode"):
        calls.clear()
        cfg = {
            "session_folder_id": "fld1",
            "agent_name": "henry",
            "client": client_name,
        }
        state = {"session_id": "s1"}
        c = FakeClient(base_url="http://x", api_key="k")

        stream_user_message(c, cfg, state, "hello")
        stream_tool_use(
            c,
            cfg,
            state,
            HookEvent(
                kind="tool_use",
                tool_name="bash",
                tool_input={"command": "echo hi"},
                tool_response={"stdout": "hi"},
            ),
        )
        stream_assistant_message(
            c,
            cfg,
            state,
            HookEvent(
                kind="stop",
                last_assistant_message="done.",
            ),
        )
        stream_session_end(c, cfg, state, HookEvent(kind="session_end"))

        for body in calls:
            assert (
                body.get("metadata", {}).get("client") == client_name
            ), f"{client_name}: missing client facet in {body}"


def test_model_metadata_flows_through_stream_paths():
    from stashai.plugin.event import HookEvent
    from stashai.plugin.hooks import (
        _event_metadata,
        stream_assistant_message,
        stream_session_end,
        stream_tool_use,
        stream_user_message,
    )
    from stashai.plugin.stash_client import StashClient

    calls = []

    class FakeClient(StashClient):
        def _post(self, path, **kwargs):
            calls.append(kwargs.get("json", {}))
            return {}

    cfg = {"session_folder_id": "fld1", "agent_name": "henry", "client": "codex_cli"}
    state = {"session_id": "s1"}
    c = FakeClient(base_url="http://x", api_key="k")
    extras = {"model": "gpt-4o", "permission_mode": "default"}
    cwd = str(Path.cwd())
    assert _event_metadata(HookEvent(kind="prompt", extras=extras)) == extras

    stream_user_message(
        c,
        cfg,
        state,
        "hello",
        HookEvent(kind="prompt", prompt_text="hello", cwd=cwd, extras=extras),
    )
    stream_tool_use(
        c,
        cfg,
        state,
        HookEvent(
            kind="tool_use",
            tool_name="bash",
            cwd=cwd,
            tool_input={"command": "echo hi"},
            tool_response={"stdout": "hi"},
            extras=extras,
        ),
    )
    stream_assistant_message(
        c,
        cfg,
        state,
        HookEvent(
            kind="stop",
            cwd=cwd,
            last_assistant_message="done.",
            extras=extras,
        ),
    )
    stream_session_end(
        c,
        cfg,
        state,
        HookEvent(
            kind="session_end",
            cwd=cwd,
            extras=extras,
        ),
    )

    for body in calls:
        assert body["metadata"].get("model") == "gpt-4o", body
        assert body["metadata"]["permission_mode"] == "default"
        assert body["metadata"]["client"] == "codex_cli"


def test_stream_session_end_not_emitted_on_assistant_message():
    """stream_assistant_message must NOT emit a session_end event — that's
    the whole point of splitting it from stream_session_end."""
    from stashai.plugin.event import HookEvent
    from stashai.plugin.hooks import stream_assistant_message
    from stashai.plugin.stash_client import StashClient

    calls = []

    class FakeClient(StashClient):
        def _post(self, path, **kwargs):
            calls.append(kwargs.get("json", {}))
            return {}

    c = FakeClient(base_url="http://x", api_key="k")
    cfg = {"session_folder_id": "fld1", "agent_name": "henry", "client": "claude_code"}
    state = {"session_id": "s1"}
    stream_assistant_message(
        c,
        cfg,
        state,
        HookEvent(
            kind="stop",
            last_assistant_message="turn complete.",
        ),
    )

    event_types = [b.get("event_type") for b in calls]
    assert "assistant_message" in event_types
    assert "session_end" not in event_types
