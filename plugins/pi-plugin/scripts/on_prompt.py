#!/usr/bin/env python3
"""Pi user_message: stream prompt to Stash."""

from adapt import adapt_prompt
from config import (
    DATA_DIR,
    get_client,
    get_config,
    get_stdin_data,
    is_configured,
    is_fusion_managed,
)

from stashai.plugin.hooks import stream_user_message
from stashai.plugin.state import load_state


def main():
    if not is_configured():
        return
    event = adapt_prompt(get_stdin_data())
    if is_fusion_managed(event.cwd):
        return
    cfg = get_config()
    state = load_state(DATA_DIR)

    # A failed upload must surface to the hook runner, not vanish silently.
    with get_client() as client:
        stream_user_message(client, cfg, state, event.prompt_text, event)


if __name__ == "__main__":
    main()
