#!/usr/bin/env python3
"""SessionStart hook: record the session ID for later activity streaming."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_stdin_data, is_configured, load_state, save_state


def main():
    if not is_configured():
        return
    data = get_stdin_data()
    state = load_state()
    state["session_id"] = data.get("session_id", "")
    save_state(state)


if __name__ == "__main__":
    main()
