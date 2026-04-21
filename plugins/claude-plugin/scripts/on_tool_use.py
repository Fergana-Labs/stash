#!/usr/bin/env python3
"""PostToolUse (async): stream tool call + result to Stash history."""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from stashai.plugin.hooks import stream_tool_use
from stashai.plugin.state import load_state

from adapt import adapt_tool_use


def main():
    if not is_configured():
        return

    state = load_state(DATA_DIR)

    event = adapt_tool_use(get_stdin_data())
    if not event.tool_name:
        return

    cfg = get_config()
    try:
        with get_client() as client:
            stream_tool_use(client, cfg, state, event, DATA_DIR)
    except Exception:
        pass


if __name__ == "__main__":
    main()
