"""Concurrent Codex sessions must not steal each other's identity or cooldown."""

import runpy
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from stashai.plugin import hooks, state, transcript_upload
from stashai.plugin.event import HookEvent

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "scripts", ["plugins/codex-plugin/scripts", "stashai/plugin/assets/codex/scripts"]
)
@pytest.mark.parametrize("event_id,expected", [("session-a", "session-a"), ("", "session-b")])
def test_stop_upload_uses_event_identity_before_shared_state(
    monkeypatch, tmp_path, scripts, event_id, expected
):
    event = HookEvent(kind="stop", session_id=event_id, transcript_path="a.jsonl", cwd="/repo")
    cfg = {"agent_name": "codex", "api_endpoint": "https://example.test", "api_key": "test"}
    config = SimpleNamespace(
        DATA_DIR=tmp_path,
        get_client=lambda: nullcontext(None),
        get_config=lambda: cfg,
        get_stdin_data=lambda: {},
        is_configured=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "adapt", SimpleNamespace(adapt_stop=lambda _: event))
    monkeypatch.setattr(state, "load_state", lambda _: {"session_id": "session-b"})
    monkeypatch.setattr(hooks, "remember_transcript_path", lambda *a: None)
    monkeypatch.setattr(hooks, "stream_assistant_message", lambda *a: None)
    monkeypatch.setattr(hooks, "upload_health_warning", lambda *a: None)
    calls = []
    monkeypatch.setattr(transcript_upload, "spawn_transcript_upload", lambda **kw: calls.append(kw))
    runpy.run_path(str(ROOT / scripts / "on_stop.py"), run_name="__main__")
    assert calls[0]["session_id"] == expected
    assert calls[0]["transcript_path"] == "a.jsonl"


def test_upload_cooldown_does_not_suppress_another_session(monkeypatch, tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text("{}\n")
    calls = []
    monkeypatch.setattr(transcript_upload.subprocess, "Popen", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(transcript_upload.time, "time", lambda: 1000)

    def spawn(sid):
        return transcript_upload.spawn_transcript_upload(
            tmp_path, str(path), sid, "codex", "/repo", "https://example.test", "test"
        )

    assert spawn("session-a")
    assert spawn("session-b")
    assert not spawn("session-a")
    assert len(calls) == 2
    monkeypatch.setattr(transcript_upload.time, "time", lambda: 1061)
    assert spawn("session-a")
