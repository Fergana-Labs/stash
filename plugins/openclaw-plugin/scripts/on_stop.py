#!/usr/bin/env python3
"""message:sent (success=true) -> stream the assistant's outbound message.

Openclaw emits `message:sent` per turn (every time the agent responds on a
channel). This hook pushes `assistant_message`; session_end is separate
(command:reset / command:stop) so we never emit a bogus session_end here.
"""

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
        print(color_upload_health_warning(warning))


if __name__ == "__main__":
    main()
