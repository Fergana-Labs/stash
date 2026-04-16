#!/usr/bin/env python3
"""message:received -> stream user prompt.

Openclaw has no prompt-modification protocol at the gateway level (messages
are forwarded raw to the underlying coding agent), so this hook only streams.
Context injection is the delegated agent's responsibility.
"""

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

    if not state.get("streaming_enabled", True):
        return

    try:
        with get_client() as client:
            stream_user_message(client, cfg, state, event.prompt_text)
    except Exception:
        pass


if __name__ == "__main__":
    main()
