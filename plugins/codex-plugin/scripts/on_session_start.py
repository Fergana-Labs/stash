#!/usr/bin/env python3
"""Codex SessionStart: save session_id for downstream streaming."""

from config import DATA_DIR, get_stdin_data, is_configured
from state import load_state, reset_stats, save_state

from adapt import adapt_session_start


def main():
    if not is_configured():
        return
    event = adapt_session_start(get_stdin_data())
    state = load_state(DATA_DIR)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)


if __name__ == "__main__":
    main()
