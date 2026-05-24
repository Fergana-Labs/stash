"""Unit tests for the JSONL → history_events parser."""

import gzip
import json
from datetime import UTC, datetime

from backend.services.transcript_import import parse_jsonl_to_events


def _line(**kw) -> str:
    return json.dumps(kw)


def test_parses_user_and_assistant_text():
    body = (
        "\n".join(
            [
                _line(type="user", message={"content": "hi"}, timestamp="2026-05-10T00:00:00Z"),
                _line(
                    type="assistant",
                    message={"content": [{"type": "text", "text": "hey"}]},
                    timestamp="2026-05-10T00:00:01Z",
                ),
            ]
        )
        + "\n"
    ).encode()
    events = parse_jsonl_to_events(body, session_id="s1", agent_name="claude")
    assert len(events) == 2
    assert events[0]["event_type"] == "user_message"
    assert events[0]["content"] == "hi"
    assert events[0]["session_id"] == "s1"
    assert events[0]["agent_name"] == "claude"
    assert events[1]["event_type"] == "assistant_message"
    assert events[1]["content"] == "hey"
    assert events[0]["created_at"] == datetime(2026, 5, 10, 0, 0, 0, tzinfo=UTC)


def test_handles_gzipped_input():
    body = _line(type="user", message={"content": "compressed"}).encode() + b"\n"
    gz = gzip.compress(body)
    events = parse_jsonl_to_events(gz, session_id="s2", agent_name="claude")
    assert len(events) == 1
    assert events[0]["content"] == "compressed"


def test_surfaces_tool_use_blocks_as_events():
    body = (
        _line(
            type="assistant",
            message={
                "content": [
                    {"type": "text", "text": "Let me read that file"},
                    {"type": "tool_use", "name": "Read", "input": {"file": "x.py"}},
                ]
            },
        )
        + "\n"
    ).encode()
    events = parse_jsonl_to_events(body, session_id="s3", agent_name="claude")
    assert [e["event_type"] for e in events] == ["assistant_message", "tool_use"]
    assert events[1]["tool_name"] == "Read"
    assert "x.py" in events[1]["content"]


def test_parses_codex_response_items():
    body = (
        "\n".join(
            [
                _line(type="session_meta", payload={"id": "codex-1"}),
                _line(
                    type="response_item",
                    payload={
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "rules"}],
                    },
                ),
                _line(
                    type="response_item",
                    payload={
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "fix the build"}],
                    },
                    timestamp="2026-05-10T00:00:00Z",
                ),
                _line(
                    type="response_item",
                    payload={
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "running tests"}],
                    },
                    timestamp="2026-05-10T00:00:01Z",
                ),
                _line(
                    type="response_item",
                    payload={
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": {"cmd": "pytest"},
                    },
                ),
                _line(
                    type="response_item",
                    payload={"type": "function_call_output", "output": "passed"},
                ),
            ]
        )
        + "\n"
    ).encode()

    events = parse_jsonl_to_events(body, session_id="codex-1", agent_name="codex")

    assert [event["event_type"] for event in events] == [
        "user_message",
        "assistant_message",
        "tool_use",
        "tool_result",
    ]
    assert [event["content"] for event in events[:2]] == ["fix the build", "running tests"]
    assert events[2]["tool_name"] == "exec_command"
    assert events[2]["content"] == '{"cmd": "pytest"}'
    assert events[3]["content"] == "passed"


def test_skips_unknown_types_and_invalid_json():
    body = (
        _line(type="system", message={"content": "ignored"})
        + "\nnot json at all\n"
        + _line(type="user", message={"content": "kept"})
        + "\n"
    ).encode()
    events = parse_jsonl_to_events(body, session_id="s4", agent_name="claude")
    assert len(events) == 1
    assert events[0]["content"] == "kept"


def test_empty_input_returns_empty_list():
    assert parse_jsonl_to_events(b"", session_id="s5", agent_name="claude") == []
    assert parse_jsonl_to_events(b"\n\n", session_id="s5", agent_name="claude") == []


def test_skips_empty_content():
    body = (_line(type="user", message={"content": ""}) + "\n").encode()
    assert parse_jsonl_to_events(body, session_id="s6", agent_name="claude") == []
