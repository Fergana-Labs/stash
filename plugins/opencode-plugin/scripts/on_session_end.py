#!/usr/bin/env python3
"""SessionEnd: spawn `opencode run <SLEEP_PROMPT>` headless to curate.

Gated by the central `auto_curate` flag plus the shared 30-min cooldown.
"""

from config import DATA_DIR, is_configured
from state import load_state, save_state

from curate_spawn import spawn_curation


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    if state.get("streaming_enabled", True):
        spawn_curation("opencode", ["run"])
    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
