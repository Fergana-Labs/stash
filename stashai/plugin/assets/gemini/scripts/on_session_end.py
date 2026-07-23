#!/usr/bin/env python3
"""SessionEnd: push session_end."""

from adapt import adapt_session_end
from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured

from stashai.plugin.hooks import finalize_session_upload, stream_session_end
from stashai.plugin.state import load_state, save_state


def main():
    if not is_configured():
        return

    state = load_state(DATA_DIR)
    cfg = get_config()

    event = adapt_session_end(get_stdin_data())
    try:
        with get_client() as client:
            stream_session_end(client, cfg, state, event)
            finalize_session_upload(client, cfg, state, event, DATA_DIR)
    except Exception:
        pass

    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
