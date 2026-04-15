#!/usr/bin/env python3
"""SessionEnd: spawn `claude -p <SLEEP_PROMPT>` headless to curate the wiki.

Gated by the central `auto_curate` flag, the shared 30-min cooldown, and the
OCTOPUS_SKIP_AUTO_CURATE=1 recursion guard so the spawned sleep session
doesn't re-trigger itself.
"""

from config import DATA_DIR, get_config, is_configured
from state import load_state, save_state

from curate_spawn import spawn_curation


def main():
    if not is_configured():
        return

    cfg = get_config()
    if not cfg.get("workspace_id"):
        return

    state = load_state(DATA_DIR)
    if not state.get("streaming_enabled", True):
        return

    spawn_curation("claude", ["-p"])

    state["session_id"] = ""
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
