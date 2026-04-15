#!/usr/bin/env python3
"""afterAgentResponse: stream the final assistant text for the turn.

Cursor's `stop` event has no assistant text; `afterAgentResponse` is the only
place to capture it. Payload: {text: "..."}.
"""

from config import DATA_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import stream_stop
from state import load_state

from adapt import adapt_agent_response


def main():
    if not is_configured():
        return
    state = load_state(DATA_DIR)
    if not state.get("streaming_enabled", True):
        return
    event = adapt_agent_response(get_stdin_data())
    if not event.last_assistant_message:
        return
    cfg = get_config()
    try:
        with get_client() as client:
            stream_stop(client, cfg, state, event)
    except Exception:
        pass


if __name__ == "__main__":
    main()
