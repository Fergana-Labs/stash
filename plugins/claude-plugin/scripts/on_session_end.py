#!/usr/bin/env python3
"""SessionEnd: spawn a detached `claude -p /octopus:sleep` to re-index the wiki.

Gated by auto_curate flag, a 30-min cooldown, and a recursion guard
(OCTOPUS_SKIP_AUTO_CURATE=1) so the spawned sleep session doesn't re-trigger.
"""

import os
import shutil
import subprocess
import time

from config import DATA_DIR, get_config, is_configured
from state import load_state, save_state

COOLDOWN_SECONDS = 30 * 60


def main():
    if os.environ.get("OCTOPUS_SKIP_AUTO_CURATE") == "1":
        return
    if not is_configured():
        return

    cfg = get_config()
    if str(cfg.get("auto_curate", "true")).lower() != "true":
        return
    if not cfg["workspace_id"]:
        return

    state = load_state(DATA_DIR)
    if not state.get("streaming_enabled", True):
        return

    now = time.time()
    if now - (state.get("last_curate_at", 0) or 0) < COOLDOWN_SECONDS:
        return

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return

    env = os.environ.copy()
    env["OCTOPUS_SKIP_AUTO_CURATE"] = "1"

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
    save_state(DATA_DIR, state)


if __name__ == "__main__":
    main()
