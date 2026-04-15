#!/usr/bin/env python3
"""SessionEnd hook: spawn a headless `claude -p /octopus:sleep` to re-index the wiki.

Runs detached so it doesn't block session teardown. Gated by the `auto_curate`
config flag, a cooldown, and a recursion guard (OCTOPUS_SKIP_AUTO_CURATE=1) so
the spawned sleep session doesn't re-trigger itself.
"""

import os
import sys
import time
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, is_configured, load_state, save_state

COOLDOWN_SECONDS = 30 * 60  # skip if we curated in the last 30 min


def main():
    # Recursion guard: the headless `claude -p` we spawn will itself fire SessionEnd.
    if os.environ.get("OCTOPUS_SKIP_AUTO_CURATE") == "1":
        return

    if not is_configured():
        return

    cfg = get_config()
    if str(cfg.get("auto_curate", "true")).lower() != "true":
        return

    if not cfg["workspace_id"]:
        return

    state = load_state()
    if not state.get("streaming_enabled", True):
        return

    now = time.time()
    last = state.get("last_curate_at", 0) or 0
    if now - last < COOLDOWN_SECONDS:
        return

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return

    env = os.environ.copy()
    env["OCTOPUS_SKIP_AUTO_CURATE"] = "1"

    # Detach: new session, stdio to /dev/null, no wait. Fire-and-forget.
    try:
        subprocess.Popen(
            [claude_bin, "-p", "/octopus:sleep"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        return

    state["last_curate_at"] = now
    save_state(state)


if __name__ == "__main__":
    main()
