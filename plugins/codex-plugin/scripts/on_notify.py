#!/usr/bin/env python3
"""Codex `notify` fallback: fires at turn end on every Codex version.

Use this when you're on a Codex build without `features.codex_hooks` enabled.
Registered via the top-level `notify` array in ~/.codex/config.toml.

Codex's notify passes the JSON payload as argv[-1] (not stdin), and child
stdin/stdout/stderr are nulled — we can't return anything or read stdin.

Turn-end semantics only. Uses state["session_id"] (from SessionStart),
not the notify payload's `thread-id`, to keep session correlation
consistent with the codex_hooks path.

Safe to enable alongside codex_hooks: this script self-suppresses when
the codex_hooks Stop heartbeat is fresh, so newer Codex builds get one
event per turn while older builds still get full coverage from notify.
"""

import json
import sys

from config import DATA_DIR, get_client, get_config, is_configured
from hooks import stream_assistant_message
from state import codex_hooks_recently_active, load_state

from adapt import adapt_notify


def _parse_argv() -> dict:
    if len(sys.argv) < 2:
        return {}
    try:
        payload = json.loads(sys.argv[-1])
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def main():
    if not is_configured():
        return
    if codex_hooks_recently_active():
        return
    state = load_state(DATA_DIR)
    if not state.get("streaming_enabled", True):
        return

    data = _parse_argv()
    if data.get("type") != "agent-turn-complete":
        return

    event = adapt_notify(data)
    cfg = get_config()
    try:
        with get_client() as client:
            stream_assistant_message(client, cfg, state, event)
    except Exception:
        pass


if __name__ == "__main__":
    main()
