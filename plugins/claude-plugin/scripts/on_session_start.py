#!/usr/bin/env python3
"""SessionStart: save session_id for downstream streaming, and inject a
context message so the agent knows the stash CLI is on its PATH."""

import json
import sys

from config import DATA_DIR, get_stdin_data, is_configured
from stashai.plugin.state import load_state, reset_stats, save_state

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


def main():
    if not is_configured():
        return

    event = adapt_session_start(get_stdin_data())

    state = load_state(DATA_DIR)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": CONTEXT,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
