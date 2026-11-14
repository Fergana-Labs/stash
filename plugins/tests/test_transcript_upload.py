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
    assert len(calls) == 2
    assert all(not any(a.startswith("--delay=") for a in c[0]) for c in calls)
    monkeypatch.setattr(transcript_upload.time, "time", lambda: 1061)
    assert spawn("session-a")
    assert not any(a.startswith("--delay=") for a in calls[2][0])


CLAUDE_SCRIPTS = ["plugins/claude-plugin/scripts", "stashai/plugin/assets/claude/scripts"]


def _run_claude_stop(monkeypatch, tmp_path, scripts, *, allowed=True):
    event = HookEvent(kind="stop", session_id="session-a", transcript_path="a.jsonl", cwd="/repo")
    cfg = {"agent_name": "claude", "api_endpoint": "https://example.test", "api_key": "test"}
    config = SimpleNamespace(
        DATA_DIR=tmp_path,
        get_client=lambda: nullcontext(None),
        get_config=lambda: cfg,
        get_stdin_data=lambda: {},
        is_configured=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "adapt", SimpleNamespace(adapt_stop=lambda _: event))
    monkeypatch.setattr(state, "load_state", lambda _: {})
    monkeypatch.setattr(hooks, "stream_assistant_message", lambda *a: None)
    monkeypatch.setattr(hooks, "upload_health_warning", lambda *a: None)
    monkeypatch.setattr(hooks, "_short_circuit", lambda *a: not allowed)
    calls = []
    monkeypatch.setattr(transcript_upload, "spawn_transcript_upload", lambda **kw: calls.append(kw))
    runpy.run_path(str(ROOT / scripts / "on_stop.py"), run_name="__main__")
    return calls


@pytest.mark.parametrize("scripts", CLAUDE_SCRIPTS)
def test_claude_stop_uploads_the_transcript_without_subagents(monkeypatch, tmp_path, scripts):
    calls = _run_claude_stop(monkeypatch, tmp_path, scripts)
    assert len(calls) == 1
    assert calls[0]["session_id"] == "session-a"
    assert calls[0]["transcript_path"] == "a.jsonl"
    assert calls[0]["include_subagents"] is False


@pytest.mark.parametrize("scripts", CLAUDE_SCRIPTS)
def test_claude_stop_uploads_nothing_when_recording_is_off(monkeypatch, tmp_path, scripts):
    assert _run_claude_stop(monkeypatch, tmp_path, scripts, allowed=False) == []


@pytest.mark.parametrize("include,expected", [(True, []), (False, ["--skip-subagents"])])
def test_spawn_passes_the_subagent_choice_to_the_upload_process(
    monkeypatch, tmp_path, include, expected
):
    path = tmp_path / "transcript.jsonl"
    path.write_text("{}\n")
    calls = []
    monkeypatch.setattr(transcript_upload.subprocess, "Popen", lambda *a, **kw: calls.append(a[0]))
    assert transcript_upload.spawn_transcript_upload(
        tmp_path,
        str(path),
        "session-a",
        "claude",
        "/repo",
        "https://example.test",
        "test",
        include_subagents=include,
    )
    assert calls[0][9:] == expected


def test_turn_inside_the_cooldown_schedules_one_delayed_upload(monkeypatch, tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text("{}\n")
    calls = []
    monkeypatch.setattr(transcript_upload.subprocess, "Popen", lambda *a, **kw: calls.append(a[0]))
    now = [1000.0]
    monkeypatch.setattr(transcript_upload.time, "time", lambda: now[0])

    def spawn():
        return transcript_upload.spawn_transcript_upload(
            tmp_path, str(path), "session-a", "claude", "/repo", "https://example.test", "test"
        )

    assert spawn()
    now[0] = 1020.0
    assert spawn()
    assert calls[1][-1] == "--delay=40"
    now[0] = 1050.0
    assert not spawn()
    assert len(calls) == 2
    now[0] = 1065.0
    assert spawn()
    assert calls[2][-1] == "--delay=55"
    now[0] = 1200.0
    assert spawn()
    assert not any(a.startswith("--delay=") for a in calls[3])


def test_upload_process_waits_for_the_delay(monkeypatch, tmp_path):
    from stashai.plugin import _do_upload

    path = tmp_path / "transcript.jsonl"
    path.write_text("{}\n")
    events = []

    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def upload_transcript(self, **kw):
            events.append("upload")

    monkeypatch.setattr(_do_upload, "StashClient", Client)
    monkeypatch.setattr(_do_upload.time, "sleep", lambda s: events.append(("sleep", s)))
    monkeypatch.setattr(sys, "argv", [
        "_do_upload.py", str(path), "session-a", "claude", "/repo",
        "https://example.test", "test", str(tmp_path), "--skip-subagents", "--delay=40",
    ])
    _do_upload.main()
    assert events == [("sleep", 40.0), "upload"]
