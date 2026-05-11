#!/usr/bin/env python3
"""Cursor sessionStart: save session_id and create the session stash."""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from stashai.plugin.hooks import create_session_stash, reset_session_stash_state
from stashai.plugin.state import load_state, reset_stats, save_state

from adapt import adapt_session_start


def main():
    if not is_configured():
        return
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)
    reset_session_stash_state(state)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)
    state = load_state(DATA_DIR)

    try:
        with get_client() as client:
            create_session_stash(client, cfg, state, event, DATA_DIR)
    except Exception:
        pass


if __name__ == "__main__":
    main()
