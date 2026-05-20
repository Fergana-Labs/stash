from __future__ import annotations

from stashai.plugin import hooks
from stashai.plugin.event import HookEvent
from stashai.plugin.hooks import (
    color_upload_health_warning,
    upload_health_warning,
    uploads_disabled_warning,
    uploads_enabled,
)
from stashai.plugin.state import load_state
from stashai.plugin.upload_status import record_upload_failure, record_upload_success


def _cfg() -> dict:
    return {
        "workspace_id": "ws1",
        "api_key": "k",
        "agent_name": "henry",
        "client": "codex_cli",
    }


def _event(session_id: str) -> HookEvent:
    return HookEvent(kind="stop", session_id=session_id, cwd="/repo")


def test_upload_health_warning_is_once_per_session(tmp_path):
    record_upload_failure(tmp_path, "event", "offline")
    state = {"session_id": "s1"}

    warning = upload_health_warning(_cfg(), state, _event("s1"), tmp_path)

    assert warning == (
        "Stash uploads are failing; this conversation may not be visible to your team. "
        "Run `stash status` for details."
    )
    assert load_state(tmp_path)["upload_warning_session_id"] == "s1"
    assert upload_health_warning(_cfg(), state, _event("s1"), tmp_path) is None


def test_upload_health_warning_resets_for_next_session(tmp_path):
    record_upload_failure(tmp_path, "event", "offline")
    state = {"session_id": "s1"}

    assert upload_health_warning(_cfg(), state, _event("s1"), tmp_path)
    state["session_id"] = "s2"

    assert upload_health_warning(_cfg(), state, _event("s2"), tmp_path)
    assert load_state(tmp_path)["upload_warning_session_id"] == "s2"


def test_upload_health_warning_skips_when_uploads_are_healthy(tmp_path):
    record_upload_success(tmp_path, "event")

    assert upload_health_warning(_cfg(), {"session_id": "s1"}, _event("s1"), tmp_path) is None


def test_color_upload_health_warning_wraps_ansi_yellow():
    assert color_upload_health_warning("message") == "\033[33mmessage\033[0m"


def test_uploads_enabled_requires_auth_and_workspace(monkeypatch):
    monkeypatch.setattr(hooks, "_read_user_config", lambda: {})

    assert uploads_enabled(_cfg(), _event("s1"))

    missing_key = {**_cfg(), "api_key": ""}
    assert not uploads_enabled(missing_key, _event("s1"))

    missing_workspace = {**_cfg(), "workspace_id": ""}
    assert not uploads_enabled(missing_workspace, HookEvent(kind="stop", session_id="s1"))


def test_uploads_disabled_warning_is_once_per_session(monkeypatch, tmp_path):
    monkeypatch.setattr(hooks.shutil, "which", lambda name: "/usr/local/bin/stash")
    monkeypatch.setattr(hooks, "_read_user_config", lambda: {})
    state = {}
    cfg = {**_cfg(), "api_key": ""}

    warning = uploads_disabled_warning(cfg, state, _event("s1"), tmp_path)

    assert warning == (
        "Hey btw, Stash uploads aren't enabled. Run `stash connect` or `stash start` "
        "to enable them."
    )
    assert load_state(tmp_path)["uploads_disabled_warning_session_id"] == "s1"
    assert uploads_disabled_warning(cfg, state, _event("s1"), tmp_path) is None

    assert uploads_disabled_warning(cfg, state, _event("s2"), tmp_path)
    assert load_state(tmp_path)["uploads_disabled_warning_session_id"] == "s2"


def test_uploads_disabled_warning_requires_stash_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(hooks.shutil, "which", lambda name: None)
    monkeypatch.setattr(hooks, "_read_user_config", lambda: {})

    warning = uploads_disabled_warning({**_cfg(), "api_key": ""}, {}, _event("s1"), tmp_path)

    assert warning is None
