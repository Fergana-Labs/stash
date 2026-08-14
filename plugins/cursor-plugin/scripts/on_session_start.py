#!/usr/bin/env python3
"""Cursor sessionStart: save session_id and create the session record."""

from adapt import adapt_session_start
from config import DATA_DIR, get_client, get_config, get_stdin_data

from stashai.plugin.hooks import (
    color_upload_health_warning,
    create_session_record,
    reset_session_record_state,
    uploads_disabled_warning,
    uploads_enabled,
)
from stashai.plugin.state import load_state, reset_stats, save_state


def main():
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)
    if not uploads_enabled(cfg):
        warning = uploads_disabled_warning(cfg, state, event, DATA_DIR)
        if warning:
            print(color_upload_health_warning(warning))
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
        pass


if __name__ == "__main__":
    main()
