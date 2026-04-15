#!/usr/bin/env python3
"""SessionStart: save session_id + warm the context cache."""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import warm_cache
from state import load_state, save_state

from adapt import adapt_session_start


def main():
    if not is_configured():
        return

    event = adapt_session_start(get_stdin_data())

    state = load_state(DATA_DIR)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)

    cfg = get_config()
    try:
        with get_client() as client:
            warm_cache(client, cfg, DATA_DIR)
    except Exception:
        pass


if __name__ == "__main__":
    main()
