#!/usr/bin/env python3
"""Stop: Codex has no separate SessionEnd, so we clear state here too."""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import stream_stop
from state import load_state, save_state

from adapt import adapt_stop


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    if not state.get("streaming_enabled", True):
        return
    event = adapt_stop(get_stdin_data())
    cfg = get_config()
    try:
        with get_client() as client:
            stream_stop(client, cfg, state, event)
    except Exception:
        pass
    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
