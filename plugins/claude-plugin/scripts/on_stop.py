#!/usr/bin/env python3
"""Stop: stream the assistant's final message and upload the transcript so far.

Claude Code's Stop hook fires per-turn (every time the model finishes
responding), not per-session. session_end lives in on_session_end.py, which
also uploads the final transcript and any subagent transcripts.

Transcript upload is spawned as a detached background process (so it doesn't
block the hook timeout) with a 60s cooldown between uploads per session.
"""

import json

from adapt import adapt_stop
from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured

from stashai.plugin.hooks import (
    color_upload_health_warning,
    recording_allowed,
    stream_assistant_message,
    upload_health_warning,
)
from stashai.plugin.state import load_state
from stashai.plugin.transcript_upload import spawn_transcript_upload


def main():
    if not is_configured():
        return

    state = load_state(DATA_DIR)

    event = adapt_stop(get_stdin_data())
    cfg = get_config()

    try:
        with get_client() as client:
            stream_assistant_message(client, cfg, state, event)
    except Exception:
        pass

    if recording_allowed(cfg, state, event):
        spawn_transcript_upload(
            data_dir=DATA_DIR,
            transcript_path=event.transcript_path,
            session_id=event.session_id or state.get("session_id", ""),
            agent_name=cfg["agent_name"],
            cwd=event.cwd,
            base_url=cfg["api_endpoint"],
            api_key=cfg["api_key"],
            include_subagents=False,
        )

    warning = upload_health_warning(cfg, state, event, DATA_DIR)
    if warning:
        # Claude Code only shows a Stop hook's `systemMessage`; bare stdout
        # reaches the transcript, which the user never sees.
        print(json.dumps({"systemMessage": color_upload_health_warning(warning)}))


if __name__ == "__main__":
    main()
