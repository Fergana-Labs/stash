#!/usr/bin/env python3
"""Hermes post_llm_call: stream the assistant's final message for this turn.

post_llm_call fires once per turn (after the tool loop), not per-session. We
only push assistant_message here; session_end lives in on_session_end.py.
Hermes exposes no transcript path, so there is nothing to remember for the
artifact upload. Warnings go to stderr — stdout must stay valid hook JSON.
"""

import sys

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
        print(color_upload_health_warning(warning), file=sys.stderr)


if __name__ == "__main__":
    main()
    print("{}")
