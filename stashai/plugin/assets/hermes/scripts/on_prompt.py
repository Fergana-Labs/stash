#!/usr/bin/env python3
"""Hermes pre_llm_call: stream the user prompt to Stash.

pre_llm_call fires once per user turn (before the tool loop). Its stdout is a
context-injection surface — `{"context": ...}` would be added to the LLM call —
so we always answer with a `{}` no-op.
"""

from adapt import adapt_prompt
from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured

from stashai.plugin.hooks import stream_user_message
from stashai.plugin.state import load_state


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
    print("{}")
