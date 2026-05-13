from __future__ import annotations

import json
import sys

from stashai.plugin.event import HookEvent
from stashai.plugin.hooks import create_session_stash, finalize_session_stash


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
    assert state["stash_workspace_id"] == "ws1"
    assert state["transcript_path"] == "/tmp/s1.jsonl"


def test_create_session_stash_resolves_workspace_from_event_cwd(monkeypatch, tmp_path):
    from stashai.plugin import hooks

    monkeypatch.setattr(
        hooks,
        "find_manifest",
        lambda cwd: {"workspace_id": "ws-from-cwd"} if cwd == "/repo" else None,
    )
    cfg = {**_cfg(), "workspace_id": ""}
    state = {"session_id": "s1"}
    event = HookEvent(kind="session_start", session_id="s1", cwd="/repo")
    client = _FakeClient()

    url = create_session_stash(client, cfg, state, event, tmp_path)

    assert url == "https://joinstash.ai/b/b-test"
    assert client.created[0]["workspace_id"] == "ws-from-cwd"
    assert state["stash_workspace_id"] == "ws-from-cwd"


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

    assert calls == [
        {
            "stash_id": "stash-1",
            "transcript_path": "/tmp/s1.jsonl",
            "cwd": "/repo",
            "files_touched": ["app.py"],
            "workspace_id": "ws1",
            "session_id": "s1",
            "agent_name": "alice-agent",
            "base_url": "https://joinstash.ai",
            "api_key": "key",
        }
    ]


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


def test_do_stash_uploads_artifacts_without_setting_summary_status(monkeypatch, tmp_path):
    from stashai.plugin import _do_stash

    artifact = tmp_path / "app.py"
    artifact.write_text("print('hi')\n")
    uploads = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs == {"base_url": "https://joinstash.ai", "api_key": "key"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def upload_stash_artifact(self, stash_id, display_path, content):
            uploads.append((stash_id, display_path, content))

        def update_stash(self, *args, **kwargs):
            raise AssertionError("plugin should not set summary status")

    monkeypatch.setattr(_do_stash, "StashClient", FakeClient)
    monkeypatch.setattr(_do_stash, "_collect_git_files", lambda cwd: [])
    monkeypatch.setenv("STASH_FILES_TOUCHED", json.dumps([str(artifact)]))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "_do_stash.py",
            "stash-1",
            "",
            str(tmp_path),
            "ws1",
            "s1",
            "alice-agent",
            "https://joinstash.ai",
            "key",
        ],
    )

    _do_stash.main()

    assert uploads == [("stash-1", "app.py", b"print('hi')\n")]
