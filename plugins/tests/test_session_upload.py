from __future__ import annotations

import json
import sys

from stashai.plugin.event import HookEvent
from stashai.plugin.hooks import create_session_record, finalize_session_upload


class _FakeClient:
    def __init__(self):
        self.created = []

    def create_session(self, **kwargs):
        self.created.append(kwargs)
        return {
            "id": "session-row-1",
            "app_url": f"https://app.joinstash.ai/sessions/{kwargs['session_id']}",
        }


def _cfg() -> dict:
    return {
        "agent_name": "alice-agent",
        "client": "codex_cli",
        "api_endpoint": "https://joinstash.ai",
        "api_key": "key",
    }


def test_create_session_record_saves_url_and_transcript_path(tmp_path):
    state = {"session_id": "s1"}
    event = HookEvent(
        kind="session_start",
        session_id="s1",
        cwd="/repo",
        transcript_path="/tmp/s1.jsonl",
    )
    client = _FakeClient()

    url = create_session_record(client, _cfg(), state, event, tmp_path)

    assert url == "https://app.joinstash.ai/sessions/s1"
    assert client.created[0]["session_id"] == "s1"
    assert client.created[0]["cwd"] == "/repo"
    assert state["session_row_id"] == "session-row-1"
    assert state["session_url"] == "https://app.joinstash.ai/sessions/s1"
    assert state["uploaded_session_id"] == "s1"
    assert state["transcript_path"] == "/tmp/s1.jsonl"


def test_finalize_session_upload_spawns_upload_with_transcript(monkeypatch, tmp_path):
    calls = []

    def fake_spawn(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr("stashai.plugin.hooks.spawn_session_upload", fake_spawn)

    state = {
        "session_id": "s1",
        "session_row_id": "session-row-1",
        "uploaded_session_id": "s1",
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

    assert finalize_session_upload(_FakeClient(), _cfg(), state, event, tmp_path)

    assert calls == [
        {
            "session_row_id": "session-row-1",
            "transcript_path": "/tmp/s1.jsonl",
            "cwd": "/repo",
            "files_touched": ["app.py"],
            "session_id": "s1",
            "agent_name": "alice-agent",
            "base_url": "https://joinstash.ai",
            "api_key": "key",
            "data_dir": tmp_path,
        }
    ]


def test_finalize_session_upload_spawns_history_fallback_without_transcript(monkeypatch):
    calls = []

    def fake_spawn(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr("stashai.plugin.hooks.spawn_session_upload", fake_spawn)

    state = {
        "session_id": "s1",
        "session_row_id": "session-row-1",
        "uploaded_session_id": "s1",
        "cwd": "/repo",
    }
    event = HookEvent(kind="session_end", session_id="s1")

    assert finalize_session_upload(_FakeClient(), _cfg(), state, event)
    assert calls[0]["transcript_path"] == ""
    assert calls[0]["session_id"] == "s1"


def test_do_session_uploads_artifacts(monkeypatch, tmp_path):
    from stashai.plugin import _do_session_upload

    artifact = tmp_path / "app.py"
    artifact.write_text("print('hi')\n")
    uploads = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs == {
                "base_url": "https://joinstash.ai",
                "api_key": "key",
                "data_dir": str(tmp_path),
            }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def upload_session_artifact(self, session_row_id, display_path, content):
            uploads.append((session_row_id, display_path, content))

    monkeypatch.setattr(_do_session_upload, "StashClient", FakeClient)
    monkeypatch.setattr(_do_session_upload, "_collect_git_files", lambda cwd: [])
    monkeypatch.setenv("SESSION_FILES_TOUCHED", json.dumps([str(artifact)]))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "_do_session_upload.py",
            "session-row-1",
            "",
            str(tmp_path),
            "s1",
            "alice-agent",
            "https://joinstash.ai",
            "key",
            str(tmp_path),
        ],
    )

    _do_session_upload.main()

    assert uploads == [("session-row-1", "app.py", b"print('hi')\n")]
