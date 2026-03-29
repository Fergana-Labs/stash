#!/usr/bin/env python3
"""SessionStart hook: warm the local context cache and sync offline data."""

import sys
import os

# Add scripts dir to path so we can import sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_stdin_data, get_client, get_config, is_configured, load_state, save_state, save_cache, OFFLINE_DB_PATH
import offline_db


def main():
    if not is_configured():
        return

    data = get_stdin_data()
    cfg = get_config()

    # Save session ID to state
    state = load_state()
    state["session_id"] = data.get("session_id", "")
    save_state(state)

    # Ensure local offline DB exists
    offline_db.init_db(OFFLINE_DB_PATH)

    # Warm the cache and sync
    try:
        with get_client() as client:
            profile = client.whoami()

            recent_events = []
            if cfg["workspace_id"] and cfg["history_store_id"]:
                recent_events = client.query_events(
                    cfg["workspace_id"], cfg["history_store_id"], limit=20,
                )

            save_cache(profile, recent_events)

            # Sync: upload pending local events, download new cloud data
            offline_db.sync_to_cloud(OFFLINE_DB_PATH, client, cfg)
            offline_db.sync_from_cloud(OFFLINE_DB_PATH, client, cfg)
    except Exception:
        # Graceful degradation: cache stays empty, on_prompt will use local DB fallback
        pass


if __name__ == "__main__":
    main()
