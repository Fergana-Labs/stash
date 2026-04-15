#!/usr/bin/env python3
"""Codex notify fallback: fires at turn end on every Codex version.

Use this when you're on a Codex build without `features.codex_hooks` enabled.
Registered via the top-level `notify` key in ~/.codex/config.toml.

Pick ONE of codex_hooks OR notify — enabling both double-fires every turn.
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import stream_stop
from state import load_state

from adapt import adapt_notify


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    if not state.get("streaming_enabled", True):
        return

    data = get_stdin_data()
    if data.get("type") != "agent-turn-complete":
        return

    event = adapt_notify(data)
    cfg = get_config()
    try:
        with get_client() as client:
            stream_stop(client, cfg, state, event)
    except Exception:
        pass


if __name__ == "__main__":
    main()
