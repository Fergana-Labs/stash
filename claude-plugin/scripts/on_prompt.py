#!/usr/bin/env python3
"""UserPromptSubmit hook: inject scored agent context via Boozle injection API.

Cloud-first: calls POST /api/v1/agents/me/inject for four-factor scored context.
Falls back to local scoring engine when the API is unreachable.
Reads replicate_me bridge escalations from shared notification directory.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    get_config, get_client, get_stdin_data, is_configured,
    load_state, load_cache,
    load_injection_state, save_injection_state,
    load_escalations,
)
from local_scoring import build_fallback_context


def main():
    if not is_configured():
        return

    # Read hook payload from stdin
    hook_data = get_stdin_data()
    prompt_text = hook_data.get("prompt", hook_data.get("userPrompt", ""))

    # Load session injection state
    session_state = load_injection_state()

    context = None

    # --- Cloud path: call injection endpoint ---
    try:
        with get_client() as client:
            result = client.inject(
                prompt_text=prompt_text or ".",
                session_state=session_state,
            )
            context = result.get("context", "")
            # Persist updated session state
            updated_state = result.get("updated_session_state", session_state)
            save_injection_state(updated_state)
    except Exception:
        # API unreachable — fall through to local fallback
        pass

    # --- Local fallback ---
    if context is None:
        cfg = get_config()
        state = load_state()
        cache = load_cache()

        persona = state.get("persona", "")
        if not persona and cache and cache.get("profile"):
            persona = cache["profile"].get("description", "")

        recent_events = []
        if cache and cache.get("recent_events"):
            recent_events = cache["recent_events"]

        context = build_fallback_context(cfg["agent_name"], persona, recent_events)

        # Increment prompt_num locally
        session_state["prompt_num"] = session_state.get("prompt_num", 0) + 1
        save_injection_state(session_state)

    # --- Append bridge escalations ---
    escalations = load_escalations()
    if escalations:
        context += escalations

    if context:
        print(json.dumps({"additionalContext": context}))


if __name__ == "__main__":
    main()
