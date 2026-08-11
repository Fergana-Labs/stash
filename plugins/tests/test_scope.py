"""Scope gate — global switch plus per-folder exclusions.

A session streams iff the plugin is configured (an `api_key` is present in
the user CLI config), streaming has not been globally stopped
(`stopped_streaming` flag), and the session's cwd is not inside any
`excluded_paths` entry — the per-folder opt-out Stash Desktop manages. The
exclusion must be path-boundary-safe: excluding /repo must not silence
/repo2, or an unrelated project goes dark without the user ever choosing it.

Regression test: when the gate is off, no event reaches the transport.
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


def test_no_exclusions_streams_everywhere(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k"})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert scope_mod.cwd_in_scope("")
    assert scope_mod.cwd_in_scope(None)
    assert scope_mod.cwd_in_scope("/some/deep/path")


def test_excluded_folder_blocks_itself_and_children(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k", "excluded_paths": ["/w/secret"]})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert not scope_mod.cwd_in_scope("/w/secret")
    assert not scope_mod.cwd_in_scope("/w/secret/sub/dir")
    assert scope_mod.cwd_in_scope("/w/other")


def test_exclusion_is_path_boundary_safe(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k", "excluded_paths": ["/w/repo"]})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert not scope_mod.cwd_in_scope("/w/repo")
    assert scope_mod.cwd_in_scope("/w/repo2")


def test_empty_cwd_cannot_match_an_exclusion(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k", "excluded_paths": ["/w/secret"]})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert scope_mod.cwd_in_scope("")


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

    monkeypatch.setattr(hooks, "cwd_in_scope", lambda *a, **k: False)

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

    monkeypatch.setattr(hooks, "cwd_in_scope", lambda *a, **k: True)

    c = _RecordingClient()
    stream_user_message(
        c,
        {"agent_name": "a"},
        {"session_id": "s"},
        "hello",
        HookEvent(kind="prompt", cwd="/anywhere"),
    )
    assert len(c.calls) == 1


# --- Folder-scoped recording: `recorded_paths` is the include side of the
# gate. Empty/absent = record everywhere; non-empty = only sessions whose cwd
# is under an entry stream. Boundary-safe like exclusions (/repo must not
# capture /repo2), and an unprovable location (no cwd) fails closed rather
# than leaking a session the user chose not to record. ---


def test_recorded_paths_absent_streams_everywhere(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k"})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert scope_mod.cwd_in_scope("/some/deep/path")


def test_recorded_paths_scopes_recording_to_the_folder(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k", "recorded_paths": ["/work/repo"]})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert scope_mod.cwd_in_scope("/work/repo")
    assert scope_mod.cwd_in_scope("/work/repo/sub/dir")
    assert not scope_mod.cwd_in_scope("/elsewhere")


def test_recorded_paths_is_path_boundary_safe(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k", "recorded_paths": ["/work/repo"]})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert not scope_mod.cwd_in_scope("/work/repo2")


def test_recorded_paths_with_no_cwd_fails_closed(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path, {"api_key": "k", "recorded_paths": ["/work/repo"]})
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert not scope_mod.cwd_in_scope("")
    assert not scope_mod.cwd_in_scope(None)


def test_exclusions_still_carve_out_of_recorded_paths(tmp_path, monkeypatch):
    cfg = _write_config(
        tmp_path,
        {
            "api_key": "k",
            "recorded_paths": ["/work"],
            "excluded_paths": ["/work/secret"],
        },
    )
    monkeypatch.setattr(scope_mod, "_CONFIG_FILE", cfg)
    assert scope_mod.cwd_in_scope("/work/repo")
    assert not scope_mod.cwd_in_scope("/work/secret/project")
