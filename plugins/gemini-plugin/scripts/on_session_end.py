#!/usr/bin/env python3
"""SessionEnd: clear session state. No auto-curate on Gemini (no headless `-p` flag)."""

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
