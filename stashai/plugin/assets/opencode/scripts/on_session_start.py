#!/usr/bin/env python3
"""opencode session.created: save session_id for downstream streaming.

opencode only emits `session.deleted` on explicit user delete — normal quit
fires nothing. To avoid leaking the prior session_id, we treat any new session
whose id differs from state as a signal that the prior session ended. Flush a
session_end for the stale id first, then save the new one.
"""

from adapt import adapt_session_start
from config import DATA_DIR, get_client, get_config, get_stdin_data

from stashai.plugin.event import HookEvent
from stashai.plugin.hooks import (
    color_upload_health_warning,
    create_session_record,
    finalize_session_upload,
    reset_session_record_state,
    stream_session_end,
    uploads_disabled_warning,
    uploads_enabled,
)
from stashai.plugin.session_upload import spawn_skills_sync
from stashai.plugin.state import load_state, reset_stats, save_state


def _flush_stale_session(prior_sid: str, state: dict) -> None:
    cfg = get_config()
    stale_state = {**state, "session_id": prior_sid}
    stale_event = HookEvent(kind="session_end", session_id=prior_sid, cwd="")
    try:
        with get_client() as client:
            stream_session_end(client, cfg, stale_state, stale_event)
            finalize_session_upload(client, cfg, stale_state, stale_event, DATA_DIR)
    except Exception:
        pass


def main():
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)
    if not uploads_enabled(cfg, event):
        warning = uploads_disabled_warning(cfg, state, event, DATA_DIR)
        if warning:
            print(color_upload_health_warning(warning))
        return

    prior_sid = state.get("session_id", "")
    if prior_sid and prior_sid != event.session_id:
        _flush_stale_session(prior_sid, state)

    reset_session_record_state(state)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)
    state = load_state(DATA_DIR)

    try:
        with get_client() as client:
            create_session_record(client, cfg, state, event, DATA_DIR)
    except Exception:
        pass

    spawn_skills_sync(cfg, state.get("uploaded_workspace_id") or cfg.get("workspace_id", ""))


if __name__ == "__main__":
    main()
