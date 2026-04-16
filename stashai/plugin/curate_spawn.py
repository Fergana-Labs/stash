"""Spawn the user's own agent CLI in headless mode with SLEEP_PROMPT.

Every plugin's `on_session_end.py` calls `spawn_curation("<binary>", [<argv...>])`
— the shared gating (central auto_curate flag, 30-min cooldown, recursion
guard, Cursor hang timeout) lives here so all five plugins behave the same.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from stashai.plugin.sleep_prompt import SLEEP_PROMPT
from stashai.plugin.state import auto_curate_enabled, curate_cooldown_active, record_curate_run

def spawn_curation(binary: str, prompt_flags: list[str]) -> bool:
    """Spawn `binary <prompt_flags> <SLEEP_PROMPT>` detached. Return True on spawn.

    `prompt_flags` is the agent-specific argv that precedes the prompt, e.g.
    `["-p"]` for claude, `["exec"]` for codex, `["run"]` for opencode.
    """
    if os.environ.get("STASH_SKIP_AUTO_CURATE") == "1":
        return False
    if not auto_curate_enabled():
        return False
    if curate_cooldown_active():
        return False

    exe = shutil.which(binary)
    if not exe:
        return False

    env = os.environ.copy()
    env["STASH_SKIP_AUTO_CURATE"] = "1"

    argv = [exe, *prompt_flags, SLEEP_PROMPT]

    popen_kwargs = dict(
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )

    # Claim the cooldown BEFORE spawning so two concurrent SessionEnds can't
    # both pass curate_cooldown_active() and double-spawn. If the spawn then
    # fails we eat one wasted cooldown window — cheaper than two curates.
    record_curate_run()

    try:
        subprocess.Popen(argv, **popen_kwargs)
    except Exception:
        return False

    return True
