#!/usr/bin/env python3
"""SessionStart: save session_id, create the session row, upload artifacts later,
and inject context."""

import json
import os
import sys

from adapt import adapt_session_start
from config import DATA_DIR, get_config, get_stdin_data

from stashai.plugin.hooks import (
    create_session_record,
    reset_session_record_state,
    uploads_disabled_warning,
    uploads_enabled,
)
from stashai.plugin.session_upload import spawn_session_watcher
from stashai.plugin.state import load_state, reset_stats, save_state

CONTEXT = (
    "You have the `stash` CLI on your PATH. Run `stash --help` to see commands. "
    "Use it to read transcripts, pages, and history from your team's shared "
    "Stash workspace. Your activity in this repo is streamed to that workspace, "
    "so teammates' agents and humans can see what you're working on. "
    "Common reads (all support `--json`): "
    "`stash history search \"<query>\"`, "
    "`stash history query --limit 20`, "
    "`stash history agents`, "
    "`stash pages --all`."
)

SESSION_CONTEXT = (
    "\nSession record: {url}\n"
    "IMPORTANT: Always include this session record link at the end of every "
    "response you give, formatted as: Session: {url}"
)


def main():
    event = adapt_session_start(get_stdin_data())
    cfg = get_config()

    state = load_state(DATA_DIR)
    if not uploads_enabled(cfg, event):
        warning = uploads_disabled_warning(cfg, state, event, DATA_DIR)
        if warning:
            json.dump({"systemMessage": warning}, sys.stdout)
        return

    reset_session_record_state(state)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)
    state = load_state(DATA_DIR)

    session_context = ""
    try:
        from config import get_client

        with get_client() as client:
            session_url = create_session_record(client, cfg, state, event, DATA_DIR)
    except Exception:
        session_url = None

    if session_url:
        session_context = "\n" + SESSION_CONTEXT.format(url=session_url)
        spawn_session_watcher(
            agent_pid=os.getppid(),
            session_id=event.session_id,
            workspace_id=state.get("uploaded_workspace_id") or cfg.get("workspace_id", ""),
            agent_name=cfg.get("agent_name", ""),
            base_url=cfg.get("api_endpoint", ""),
            api_key=cfg.get("api_key", ""),
            cwd=event.cwd or "",
            data_dir=DATA_DIR,
            session_row_id=state.get("session_row_id", ""),
        )

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": CONTEXT + session_context,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
