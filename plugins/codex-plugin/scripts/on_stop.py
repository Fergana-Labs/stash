#!/usr/bin/env python3
"""Stop: stream the assistant's final message for this turn, then try curation.

Codex's Stop hook fires per-turn. We push assistant_message (not session_end)
and deliberately do NOT clear session_id — subsequent turns in the same
session need it for correlation. Curation is attempted on every Stop but
`spawn_curation` enforces the central 30-min cooldown, so it only actually
fires once per half-hour. Codex has no SessionEnd hook today, so this is the
only curation trigger.
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import stream_assistant_message
from state import load_state

from adapt import adapt_stop
from curate_spawn import spawn_curation


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    if not state.get("streaming_enabled", True):
        return
    event = adapt_stop(get_stdin_data())
    cfg = get_config()
    try:
        with get_client() as client:
            stream_assistant_message(client, cfg, state, event)
    except Exception:
        pass
    spawn_curation("codex", ["exec"])


if __name__ == "__main__":
    main()
