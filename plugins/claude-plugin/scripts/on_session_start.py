#!/usr/bin/env python3
"""SessionStart: save session_id, create a stash eagerly so the URL is known
from the first turn, spawn a background watcher that fills in the summary +
artifacts after the session ends, and inject context."""

import json
import os
import subprocess
import sys

from config import DATA_DIR, get_config, get_stdin_data, is_configured
from stashai.plugin.state import load_state, reset_stats, save_state
from stashai.plugin.stash_client import StashClient

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


def _create_stash(event, cfg):
    """Create the stash eagerly at session start. Returns the stash dict or None."""
    try:
        with StashClient(
            base_url=cfg["api_endpoint"], api_key=cfg["api_key"],
        ) as client:
            return client.create_stash(
                workspace_id=cfg["workspace_id"],
                session_id=event.session_id,
                agent_name=cfg["agent_name"],
                cwd=event.cwd,
                files_touched=[],
            )
    except Exception:
        return None


def _spawn_stash_watcher(event, cfg, stash_id):
    """Spawn a background process that waits for Claude Code to exit,
    then uploads artifacts and generates the summary."""
    script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "_stash_watcher_shim.py",
    )

    claude_pid = os.getppid()

    subprocess.Popen(
        [
            sys.executable, script,
            str(claude_pid),
            event.session_id,
            cfg.get("workspace_id", ""),
            cfg.get("agent_name", ""),
            cfg.get("api_endpoint", ""),
            cfg.get("api_key", ""),
            event.cwd or "",
            str(DATA_DIR),
            stash_id,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def main():
    if not is_configured():
        return

    event = adapt_session_start(get_stdin_data())
    cfg = get_config()

    state = load_state(DATA_DIR)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)

    stash_context = ""
    if cfg.get("workspace_id"):
        stash = _create_stash(event, cfg)
        if stash and stash.get("url"):
            stash_context = "\n" + STASH_CONTEXT.format(url=stash["url"])
            state["stash_id"] = str(stash["id"])
            state["stash_url"] = stash["url"]
            save_state(DATA_DIR, state)
            _spawn_stash_watcher(event, cfg, str(stash["id"]))

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
