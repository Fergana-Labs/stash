#!/usr/bin/env python3
"""SessionStart: save session_id, create a stash eagerly so the URL is known
from the first turn, spawn a background watcher that fills in the summary +
artifacts after the session ends, and inject context."""

import json
import os
import sys
from config import DATA_DIR, get_config, get_stdin_data, is_configured
from stashai.plugin.hooks import create_session_stash, reset_session_stash_state
from stashai.plugin.state import load_state, reset_stats, save_state
from stashai.plugin.stash_upload import spawn_stash_watcher

from adapt import adapt_session_start

CONTEXT = (
    "You have the `stash` CLI on your PATH. Run `stash --help` to see commands. "
    "Use it to read transcripts, notebooks, and history from your team's shared "
    "Stash workspace. Your activity in this repo is streamed to that workspace, "
    "so teammates' agents and humans can see what you're working on. "
    "Common reads (all support `--json`): "
    "`stash history search \"<query>\"`, "
    "`stash history query --limit 20`, "
    "`stash history agents`, "
    "`stash notebooks list --all`."
)

STASH_CONTEXT = (
    "\nSession stash: {url}\n"
    "IMPORTANT: Always include this session stash link at the end of every "
    "response you give, formatted as: 📦 Stash: {url}"
)


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

    stash_context = ""
    try:
        from config import get_client

        with get_client() as client:
            stash_url = create_session_stash(client, cfg, state, event, DATA_DIR)
    except Exception:
        stash_url = None

    if stash_url:
        stash_context = "\n" + STASH_CONTEXT.format(url=stash_url)
        spawn_stash_watcher(
            agent_pid=os.getppid(),
            session_id=event.session_id,
            workspace_id=state.get("stash_workspace_id") or cfg.get("workspace_id", ""),
            agent_name=cfg.get("agent_name", ""),
            base_url=cfg.get("api_endpoint", ""),
            api_key=cfg.get("api_key", ""),
            cwd=event.cwd or "",
            data_dir=DATA_DIR,
            stash_id=state.get("stash_id", ""),
        )

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": CONTEXT + stash_context,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
