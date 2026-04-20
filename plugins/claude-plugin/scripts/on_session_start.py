#!/usr/bin/env python3
"""SessionStart: save session_id for downstream streaming, and inject a
context message so the agent knows the stash CLI is on its PATH."""

import json
import sys

from config import DATA_DIR, get_stdin_data, is_configured
from stashai.plugin.state import load_state, reset_stats, save_state

from adapt import adapt_session_start

CONTEXT_CONFIGURED = (
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

CONTEXT_UNCONFIGURED = (
    "You have the `stash` CLI on your PATH but it isn't connected to a "
    "workspace yet. The user can run `stash connect` to set it up, then "
    "team transcripts and notebooks become readable via `stash history` "
    "and `stash notebooks`."
)


def emit_context(text: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": text,
            }
        },
        sys.stdout,
    )


def main():
    if not is_configured():
        emit_context(CONTEXT_UNCONFIGURED)
        return

    event = adapt_session_start(get_stdin_data())

    state = load_state(DATA_DIR)
    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)

    emit_context(CONTEXT_CONFIGURED)


if __name__ == "__main__":
    main()
