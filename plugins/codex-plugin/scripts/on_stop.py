#!/usr/bin/env python3
"""Stop: stream the assistant's final message, upload transcript, then try curation.

Codex's Stop hook fires per-turn. We push assistant_message (not session_end)
and deliberately do NOT clear session_id — subsequent turns in the same
session need it for correlation. Curation is attempted on every Stop but
`spawn_curation` enforces the central 30-min cooldown, so it only actually
fires once per half-hour. Codex has no SessionEnd hook today, so this is the
only curation trigger.

Transcript upload is spawned as a detached background process (so it doesn't
block the hook timeout) with a 60s cooldown between uploads per session.
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from stashai.plugin.hooks import stream_assistant_message
from stashai.plugin.state import load_state, mark_codex_hooks_active
from stashai.plugin.transcript_upload import spawn_transcript_upload

from adapt import adapt_stop
from stashai.plugin.curate_spawn import spawn_curation


def main():
    if not is_configured():
        return
    mark_codex_hooks_active()
    state = load_state(DATA_DIR)
    event = adapt_stop(get_stdin_data())
    cfg = get_config()
    try:
        with get_client() as client:
            stream_assistant_message(client, cfg, state, event)
    except Exception:
        pass

    spawn_transcript_upload(
        data_dir=DATA_DIR,
        transcript_path=event.transcript_path,
        session_id=state.get("session_id", ""),
        workspace_id=cfg["workspace_id"],
        agent_name=cfg["agent_name"],
        cwd=event.cwd,
        base_url=cfg["api_endpoint"],
        api_key=cfg["api_key"],
    )

    spawn_curation("codex", ["exec"])


if __name__ == "__main__":
    main()
