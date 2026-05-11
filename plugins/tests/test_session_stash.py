from __future__ import annotations

from stashai.plugin.event import HookEvent
from stashai.plugin.hooks import create_session_stash, finalize_session_stash
from stashai.plugin._do_stash import _history_text


class _FakeClient:
    def __init__(self):
        self.created = []

    def create_stash(self, **kwargs):
        self.created.append(kwargs)
        return {
            "id": "stash-1",
            "url": "https://joinstash.ai/b/b-test",
        }


def _cfg() -> dict:
    return {
        "workspace_id": "ws1",
        "agent_name": "alice-agent",
        "client": "codex_cli",
        "api_endpoint": "https://joinstash.ai",
        "api_key": "key",
    }


def test_create_session_stash_saves_url_and_transcript_path(tmp_path):
    state = {"session_id": "s1"}
    event = HookEvent(
        kind="session_start",
        session_id="s1",
        cwd="/repo",
        transcript_path="/tmp/s1.jsonl",
    )
    client = _FakeClient()

    url = create_session_stash(client, _cfg(), state, event, tmp_path)

    assert url == "https://joinstash.ai/b/b-test"
    assert client.created[0]["session_id"] == "s1"
    assert client.created[0]["cwd"] == "/repo"
    assert state["stash_id"] == "stash-1"
    assert state["stash_url"] == "https://joinstash.ai/b/b-test"
    assert state["stash_session_id"] == "s1"
    assert state["transcript_path"] == "/tmp/s1.jsonl"


def test_finalize_session_stash_spawns_upload_with_transcript(monkeypatch, tmp_path):
    calls = []

    def fake_spawn(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr("stashai.plugin.hooks.spawn_stash_upload", fake_spawn)

    state = {
        "session_id": "s1",
        "stash_id": "stash-1",
        "stash_session_id": "s1",
        "cwd": "/repo",
        "stats": {
            "tool_count": 1,
            "tools_used": ["edit"],
            "files_touched": ["app.py"],
        },
    }
    event = HookEvent(
        kind="session_end",
        session_id="s1",
        transcript_path="/tmp/s1.jsonl",
    )

    assert finalize_session_stash(_FakeClient(), _cfg(), state, event, tmp_path)

    assert calls == [{
        "stash_id": "stash-1",
        "transcript_path": "/tmp/s1.jsonl",
        "cwd": "/repo",
        "files_touched": ["app.py"],
        "workspace_id": "ws1",
        "session_id": "s1",
        "agent_name": "alice-agent",
        "base_url": "https://joinstash.ai",
        "api_key": "key",
    }]


def test_finalize_session_stash_spawns_history_fallback_without_transcript(monkeypatch):
    calls = []

    def fake_spawn(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr("stashai.plugin.hooks.spawn_stash_upload", fake_spawn)

    state = {
        "session_id": "s1",
        "stash_id": "stash-1",
        "stash_session_id": "s1",
        "cwd": "/repo",
    }
    event = HookEvent(kind="session_end", session_id="s1")

    assert finalize_session_stash(_FakeClient(), _cfg(), state, event)
    assert calls[0]["transcript_path"] == ""
    assert calls[0]["session_id"] == "s1"
    assert calls[0]["workspace_id"] == "ws1"


def test_history_text_formats_session_events_for_summary():
    class Client:
        def query_events(self, **kwargs):
            assert kwargs["workspace_id"] == "ws1"
            assert kwargs["session_id"] == "s1"
            assert kwargs["order"] == "asc"
            return [
                {
                    "created_at": "2026-05-11T00:00:00Z",
                    "event_type": "user_message",
                    "tool_name": None,
                    "content": "Fix login.",
                },
                {
                    "created_at": "2026-05-11T00:00:01Z",
                    "event_type": "tool_use",
                    "tool_name": "edit",
                    "content": "Edited auth.py",
                },
            ]

    text = _history_text(Client(), "ws1", "s1")

    assert "user_message" in text
    assert "Fix login." in text
    assert "tool_use:edit" in text
