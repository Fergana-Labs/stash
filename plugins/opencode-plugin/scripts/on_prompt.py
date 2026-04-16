#!/usr/bin/env python3
"""opencode prompt hook: stream the user's prompt to Stash history."""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import stream_user_message
from state import load_state

from adapt import adapt_prompt


def main():
    if not is_configured():
        return
    event = adapt_prompt(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)
    try:
        with get_client() as client:
            stream_user_message(client, cfg, state, event.prompt_text, event)
    except Exception:
        pass


if __name__ == "__main__":
    main()
