"""Scope gate — global, single-player streaming switch.

There is no `.stash` manifest and no cwd/path-based scope. A session streams
iff the plugin is configured (an `api_key` is present in the user CLI config)
AND streaming has not been globally stopped (`stopped_streaming` flag). The
`cwd` argument is kept only for call-site compatibility.

Regression test: when the global gate is off, no event reaches the transport.
"""

from __future__ import annotations

import json

from stashai.plugin import scope as scope_mod
from stashai.plugin.event import HookEvent


def _write_config(tmp_path, data: dict):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(data))
    return cfg


def test_configured_and_not_stopped_streams(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k"})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert scope_mod.streaming_enabled()
    assert scope_mod.cwd_in_scope("/anywhere")


def test_not_configured_does_not_stream(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"stopped_streaming": False})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert not scope_mod.streaming_enabled()
    assert not scope_mod.cwd_in_scope("/anywhere")


def test_stopped_does_not_stream(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k", "stopped_streaming": True})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert not scope_mod.streaming_enabled()
    assert not scope_mod.cwd_in_scope("/anywhere")


def test_missing_config_does_not_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", tmp_path / "config.json")
    assert not scope_mod.streaming_enabled()
    assert not scope_mod.cwd_in_scope("/anywhere")


def test_cwd_is_ignored(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k"})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert scope_mod.cwd_in_scope("")
    assert scope_mod.cwd_in_scope(None)
    assert scope_mod.cwd_in_scope("/some/deep/path")


# --- Regression: the global gate must short-circuit live events ------------


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def push_event(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


def test_gate_off_blocks_live_events(monkeypatch):
    from stashai.plugin import hooks
    from stashai.plugin.hooks import stream_user_message

    monkeypatch.setattr(hooks, "streaming_enabled", lambda: False)

    c = _RecordingClient()
    stream_user_message(
        c,
        {"agent_name": "a"},
        {"session_id": "s"},
        "hello",
        HookEvent(kind="prompt", cwd="/anywhere"),
    )
    assert c.calls == []


def test_gate_on_allows_live_events(monkeypatch):
    from stashai.plugin import hooks
    from stashai.plugin.hooks import stream_user_message

    monkeypatch.setattr(hooks, "streaming_enabled", lambda: True)

    c = _RecordingClient()
    stream_user_message(
        c,
        {"agent_name": "a"},
        {"session_id": "s"},
        "hello",
        HookEvent(kind="prompt", cwd="/anywhere"),
    )
    assert len(c.calls) == 1
