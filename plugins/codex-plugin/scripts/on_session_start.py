#!/usr/bin/env python3
"""Codex SessionStart: save session_id and create the session record."""

import json
import os

from adapt import adapt_session_start
from config import DATA_DIR, get_client, get_config, get_stdin_data

from stashai.plugin.hooks import (
    color_upload_health_warning,
    create_session_record,
    reset_session_record_state,
    uploads_disabled_warning,
    uploads_enabled,
)
from stashai.plugin.session_upload import spawn_session_watcher
from stashai.plugin.state import load_state, reset_stats, save_state


def main():
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)
    if not uploads_enabled(cfg, event):
        warning = uploads_disabled_warning(cfg, state, event, DATA_DIR)
        if warning:
            print(json.dumps({"systemMessage": color_upload_health_warning(warning)}))
        return

    reset_session_record_state(state)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)
    state = load_state(DATA_DIR)

    try:
        with get_client() as client:
            create_session_record(client, cfg, state, event, DATA_DIR)
    except Exception:
        return

    if state.get("session_row_id"):
        spawn_session_watcher(
            agent_pid=os.getppid(),
            session_id=event.session_id,
            workspace_id=state.get("uploaded_workspace_id") or cfg.get("workspace_id", ""),
            agent_name=cfg.get("agent_name", ""),
            base_url=cfg.get("api_endpoint", ""),
            api_key=cfg.get("api_key", ""),
            cwd=event.cwd or "",
            data_dir=DATA_DIR,
            session_row_id=state.get("session_row_id", ""),
            transcript_path=event.transcript_path,
        )


if __name__ == "__main__":
    main()
