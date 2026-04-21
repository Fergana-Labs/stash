#!/usr/bin/env python3
"""SessionEnd: push the session_end event, then spawn `claude -p <SLEEP_PROMPT>`
headless to curate the wiki.

Curation is gated by the central `auto_curate` flag, the shared 30-min cooldown
in `~/.stash/config.json`, and the STASH_SKIP_AUTO_CURATE=1 recursion
guard (set before spawn so the curate session doesn't re-trigger itself).
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from stashai.plugin.hooks import stream_session_end
from stashai.plugin.state import load_state, save_state

from adapt import adapt_stop
from stashai.plugin.curate_spawn import spawn_curation


def main():
    if not is_configured():
        return

    state = load_state(DATA_DIR)
    cfg = get_config()

    if cfg.get("workspace_id"):
        event = adapt_stop(get_stdin_data())
        try:
            with get_client() as client:
                stream_session_end(client, cfg, state, event)
        except Exception:
            pass

        spawn_curation("claude", ["-p"])

    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
