#!/usr/bin/env python3
"""SessionStart hook: warm the local context cache from the server."""

import sys
import os

# Add scripts dir to path so we can import sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_stdin_data, get_client, get_config, is_configured, load_state, save_state, save_cache


def main():
    if not is_configured():
        return

    data = get_stdin_data()
    cfg = get_config()

    # Save session ID to state
    state = load_state()
    state["session_id"] = data.get("session_id", "")
    save_state(state)

    # Warm the cache
    try:
        with get_client() as client:
            profile = client.whoami()

            recent_events = []
            if cfg["workspace_id"] and cfg["history_store_id"]:
                recent_events = client.query_events(
                    cfg["workspace_id"], cfg["history_store_id"], limit=20,
                )

            save_cache(profile, recent_events)
    except Exception:
        # Graceful degradation: cache stays empty, on_prompt will use cached fallback
        pass


if __name__ == "__main__":
    main()
