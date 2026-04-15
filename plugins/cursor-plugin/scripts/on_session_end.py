#!/usr/bin/env python3
"""SessionEnd: spawn `cursor-agent -p <SLEEP_PROMPT>` headless to curate.

`cursor-agent -p` has open reports of hanging — the shared spawn helper
applies a 10-minute kill-on-overrun. Gated by the central `auto_curate`
flag plus the shared 30-min cooldown.
"""

from config import DATA_DIR, is_configured
from state import load_state, save_state

from curate_spawn import spawn_curation


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    if state.get("streaming_enabled", True):
        spawn_curation("cursor-agent", ["-p"])
    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
