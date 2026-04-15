#!/usr/bin/env python3
"""SessionEnd: auto-curate disabled by default on Cursor (no headless entry point).

Users who want curation on Cursor should run `octopus curate` manually or
on a cron. This hook just clears session state.
"""

from config import DATA_DIR, is_configured
from state import load_state, save_state


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
