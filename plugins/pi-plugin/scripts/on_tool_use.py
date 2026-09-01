#!/usr/bin/env python3
"""Pi tool_use: stream tool use to Stash."""

from adapt import adapt_tool_use
from config import (
    DATA_DIR,
    get_client,
    get_config,
    get_stdin_data,
    is_configured,
    is_fusion_managed,
)

from stashai.plugin.hooks import stream_tool_use
from stashai.plugin.state import load_state


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    event = adapt_tool_use(get_stdin_data())
    if is_fusion_managed(event.cwd):
        return
    if not event.tool_name:
        return
    cfg = get_config()
    # A failed upload must surface to the hook runner, not vanish silently.
    with get_client() as client:
        stream_tool_use(client, cfg, state, event, DATA_DIR)


if __name__ == "__main__":
    main()
