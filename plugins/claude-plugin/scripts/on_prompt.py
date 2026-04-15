#!/usr/bin/env python3
"""UserPromptSubmit hook: stream the user's prompt to the Octopus history store."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, get_client, get_stdin_data, is_configured, load_state


def stream_user_message(cfg: dict, state: dict, prompt_text: str):
    if not cfg["workspace_id"]:
        return
    if not prompt_text or not prompt_text.strip():
        return
    try:
        with get_client() as client:
            client.push_event(
                workspace_id=cfg["workspace_id"],
                agent_name=cfg["agent_name"],
                event_type="user_message",
                content=prompt_text[:2000],
                session_id=state.get("session_id", ""),
            )
    except Exception:
        pass


def main():
    if not is_configured():
        return
    hook_data = get_stdin_data()
    prompt_text = hook_data.get("prompt", hook_data.get("userPrompt", ""))
    cfg = get_config()
    state = load_state()
    stream_user_message(cfg, state, prompt_text)


if __name__ == "__main__":
    main()
