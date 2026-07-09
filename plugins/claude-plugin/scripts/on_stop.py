#!/usr/bin/env python3
"""Stop: stream the assistant's final message for this turn.

Claude Code's Stop hook fires per-turn (every time the model finishes
responding), not per-session. We only push assistant_message here;
session_end lives in on_session_end.py.
"""

import json

from adapt import adapt_stop
from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured

from stashai.plugin.hooks import (
    color_upload_health_warning,
    stream_assistant_message,
    upload_health_warning,
)
from stashai.plugin.state import load_state


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
    warning = upload_health_warning(cfg, state, event, DATA_DIR)
    if warning:
        # Claude Code only shows a Stop hook's `systemMessage`; bare stdout
        # reaches the transcript, which the user never sees.
        print(json.dumps({"systemMessage": color_upload_health_warning(warning)}))


if __name__ == "__main__":
    main()
