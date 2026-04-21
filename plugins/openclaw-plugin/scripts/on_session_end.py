#!/usr/bin/env python3
"""command:reset / command:stop -> push session_end, clear state.

No auto-curation spawn: Openclaw is a chat gateway, not a coding agent with
a headless entry point. Users who want curation should run it manually or
on a cron via the matching IDE plugin for whichever agent Openclaw delegates
to (Claude Code, Codex, etc.).
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from stashai.plugin.hooks import stream_session_end
from stashai.plugin.state import load_state, save_state

from adapt import adapt_session_end


def main():
    if not is_configured():
        return

    state = load_state(DATA_DIR)
    cfg = get_config()

    if cfg.get("workspace_id"):
        event = adapt_session_end(get_stdin_data())
        try:
            with get_client() as client:
                stream_session_end(client, cfg, state, event)
        except Exception:
            pass

    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
