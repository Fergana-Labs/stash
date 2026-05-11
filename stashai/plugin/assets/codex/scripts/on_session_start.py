#!/usr/bin/env python3
"""Codex SessionStart: save session_id and create the session stash."""

import os

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from stashai.plugin.hooks import create_session_stash, reset_session_stash_state
from stashai.plugin.state import load_state, reset_stats, save_state
from stashai.plugin.stash_upload import spawn_stash_watcher

from adapt import adapt_session_start


def main():
    if not is_configured():
        return
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)
    reset_session_stash_state(state)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)
    state = load_state(DATA_DIR)

    if cfg.get("workspace_id"):
        try:
            with get_client() as client:
                create_session_stash(client, cfg, state, event, DATA_DIR)
        except Exception:
            return

        if state.get("stash_id"):
            spawn_stash_watcher(
                agent_pid=os.getppid(),
                session_id=event.session_id,
                workspace_id=cfg.get("workspace_id", ""),
                agent_name=cfg.get("agent_name", ""),
                base_url=cfg.get("api_endpoint", ""),
                api_key=cfg.get("api_key", ""),
                cwd=event.cwd or "",
                data_dir=DATA_DIR,
                stash_id=state.get("stash_id", ""),
                transcript_path=event.transcript_path,
            )


if __name__ == "__main__":
    main()
