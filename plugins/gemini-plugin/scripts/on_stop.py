#!/usr/bin/env python3
"""AfterAgent: stream the assistant's final message for this turn.

Gemini's AfterAgent fires per-turn, not per-session. We only push
assistant_message here; session_end lives in on_session_end.py.
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import stream_assistant_message
from state import load_state

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
            stream_assistant_message(client, cfg, state, event)
    except Exception:
        pass


if __name__ == "__main__":
    main()
