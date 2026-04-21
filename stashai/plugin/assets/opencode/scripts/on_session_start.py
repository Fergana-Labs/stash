#!/usr/bin/env python3
"""opencode session.created: save session_id for downstream streaming.

opencode only emits `session.deleted` on explicit user delete — normal quit
fires nothing. To avoid leaking the prior session_id and skipping curation,
we treat any new session whose id differs from state as a signal that the
prior session ended. Flush a session_end for the stale id first, then save
the new one.
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from stashai.plugin.event import HookEvent
from stashai.plugin.hooks import stream_session_end
from stashai.plugin.state import load_state, reset_stats, save_state

from adapt import adapt_session_start
from stashai.plugin.curate_spawn import spawn_curation


def _flush_stale_session(prior_sid: str, state: dict) -> None:
    cfg = get_config()
    if not cfg.get("workspace_id"):
        return
    stale_state = {**state, "session_id": prior_sid}
    stale_event = HookEvent(kind="session_end", session_id=prior_sid, cwd="")
    try:
        with get_client() as client:
            stream_session_end(client, cfg, stale_state, stale_event)
    except Exception:
        pass
    # 30-min cooldown still gates this; safe to call.
    spawn_curation("opencode", ["run"])


def main():
    if not is_configured():
        return
    event = adapt_session_start(get_stdin_data())
    state = load_state(DATA_DIR)

    prior_sid = state.get("session_id", "")
    if prior_sid and prior_sid != event.session_id:
        _flush_stale_session(prior_sid, state)

    state["session_id"] = event.session_id
    save_state(DATA_DIR, state)
    reset_stats(DATA_DIR)


if __name__ == "__main__":
    main()
