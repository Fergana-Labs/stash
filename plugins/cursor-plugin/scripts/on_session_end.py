#!/usr/bin/env python3
"""SessionEnd: push session_end, then spawn `cursor-agent -p <SLEEP_PROMPT>`
headless to curate.

`cursor-agent -p` has open reports of hanging — the shared spawn helper
applies a 10-minute kill-on-overrun. Gated by the central `auto_curate`
flag plus the shared 30-min cooldown.
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import stream_session_end
from state import load_state, save_state

from adapt import adapt_session_end
from curate_spawn import spawn_curation


def main():
    if not is_configured():
        return

    state = load_state(DATA_DIR)
    cfg = get_config()

    if state.get("streaming_enabled", True) and cfg.get("workspace_id"):
        event = adapt_session_end(get_stdin_data())
        try:
            with get_client() as client:
                stream_session_end(client, cfg, state, event)
        except Exception:
            pass

        spawn_curation("cursor-agent", ["-p"])

    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
