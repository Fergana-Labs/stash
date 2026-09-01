#!/usr/bin/env python3
"""Pi assistant_message: stream assistant message and upload transcript.

Pi's assistant_message hook fires per-turn. We push assistant_message (not
session_end) and deliberately do NOT clear session_id — subsequent turns in
the same session need it for correlation. session_end is handled separately.

Transcript upload is spawned as a detached background process (so it doesn't
block the hook timeout) with a 60s cooldown between uploads per session.
"""

import json

from adapt import adapt_stop
from config import (
    DATA_DIR,
    get_client,
    get_config,
    get_stdin_data,
    is_configured,
    is_fusion_managed,
)

from cli.formatting import echo_stdout
from stashai.plugin.hooks import (
    color_upload_health_warning,
    remember_transcript_path,
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
    if is_fusion_managed(event.cwd):
        return
    remember_transcript_path(state, event, DATA_DIR)
    cfg = get_config()
    # A failed stream must surface to the hook runner, not vanish silently.
    with get_client() as client:
        stream_assistant_message(client, cfg, state, event)

    spawn_transcript_upload(
        data_dir=DATA_DIR,
        transcript_path=event.transcript_path,
        session_id=state.get("session_id", ""),
        agent_name=cfg["agent_name"],
        cwd=event.cwd,
        base_url=cfg["api_endpoint"],
        api_key=cfg["api_key"],
        session_folder_id=cfg.get("session_folder_id", ""),
    )
    warning = upload_health_warning(cfg, state, event, DATA_DIR)
    if warning:
        echo_stdout(json.dumps({"systemMessage": color_upload_health_warning(warning)}))


if __name__ == "__main__":
    main()
