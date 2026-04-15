"""Spawn the user's own agent CLI in headless mode with SLEEP_PROMPT.

Every plugin's `on_session_end.py` calls `spawn_curation("<binary>", [<argv...>])`
— the shared gating (central auto_curate flag, 30-min cooldown, recursion
guard, Cursor hang timeout) lives here so all five plugins behave the same.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from sleep_prompt import SLEEP_PROMPT
from state import auto_curate_enabled, curate_cooldown_active, record_curate_run

# Cursor's `cursor-agent -p` has open reports of hanging indefinitely. Cap the
# subprocess lifetime so a stuck curation can never starve future sessions.
CURSOR_TIMEOUT_SECONDS = 10 * 60


def spawn_curation(binary: str, prompt_flags: list[str]) -> bool:
    """Spawn `binary <prompt_flags> <SLEEP_PROMPT>` detached. Return True on spawn.

    `prompt_flags` is the agent-specific argv that precedes the prompt, e.g.
    `["-p"]` for claude, `["exec"]` for codex, `["run"]` for opencode.
    """
    if os.environ.get("OCTOPUS_SKIP_AUTO_CURATE") == "1":
        return False
    if not auto_curate_enabled():
        return False
    if curate_cooldown_active():
        return False

    exe = shutil.which(binary)
    if not exe:
        return False

    env = os.environ.copy()
    env["OCTOPUS_SKIP_AUTO_CURATE"] = "1"

    argv = [exe, *prompt_flags, SLEEP_PROMPT]

    popen_kwargs = dict(
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )

    try:
        proc = subprocess.Popen(argv, **popen_kwargs)
    except Exception:
        return False

    if binary == "cursor-agent":
        _enforce_cursor_timeout(proc)

    record_curate_run()
    return True


def _enforce_cursor_timeout(proc: subprocess.Popen) -> None:
    """Fire-and-forget watcher that kills `cursor-agent` if it hangs past the cap."""
    import threading

    def _watch():
        try:
            proc.wait(timeout=CURSOR_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass

    t = threading.Thread(target=_watch, daemon=True)
    t.start()
