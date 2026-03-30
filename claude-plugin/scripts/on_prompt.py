#!/usr/bin/env python3
"""UserPromptSubmit hook: inject scored agent context via Boozle injection API.

Calls POST /api/v1/agents/me/inject for four-factor scored context.
Falls back to basic cached context when the API is unreachable.
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


def build_fallback_context(
    agent_name: str,
    persona: str,
    recent_events: list[dict],
) -> str:
    """Build a basic context string from cached data when API is unreachable."""
    lines = []
    lines.append("## Agent Identity")
    lines.append(f"You are **{agent_name}**, a Boozle agent.")
    if persona:
        lines.append(persona)
    lines.append("")

    if recent_events:
        lines.append("## Recent Activity (your previous sessions)")
        for event in recent_events[:15]:
            ts = event.get("created_at", "")[:16]
            tool = event.get("tool_name", "")
            content = event.get("content", "")[:200]
            event_type = event.get("event_type", "")
            if tool:
                lines.append(f"- [{ts}] {tool}: {content}")
            else:
                lines.append(f"- [{ts}] ({event_type}) {content}")
        lines.append("")

    return "\n".join(lines)


def main():
    if not is_configured():
        return

    # Read hook payload from stdin
    hook_data = get_stdin_data()
    prompt_text = hook_data.get("prompt", hook_data.get("userPrompt", ""))
    hook_session_id = hook_data.get("session_id", "")

    # Load session injection state and plugin state for session_id
    session_state = load_injection_state()
    state = load_state()
    session_id = hook_session_id or state.get("session_id", "")

    context = None

    # --- Cloud path: call injection endpoint ---
    try:
        with get_client() as client:
            result = client.inject(
                prompt_text=prompt_text or ".",
                session_state=session_state,
                session_id=session_id,
            )
            context = result.get("context", "")
            # Persist updated session state
            updated_state = result.get("updated_session_state", session_state)
            save_injection_state(updated_state)
    except Exception:
        # API unreachable — fall through to cached fallback
        pass

    # --- Cached fallback when server is unreachable ---
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
