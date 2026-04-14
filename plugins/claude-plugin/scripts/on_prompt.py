#!/usr/bin/env python3
"""UserPromptSubmit hook: stream user message + inject scored persona context.

1. Always streams the user's prompt to the Octopus history store
2. Optionally injects persona/memory context (unless inject_context=false)
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
    lines.append(f"You are **{agent_name}**, a Octopus agent.")
    if persona:
        lines.append(persona)
    lines.append("")

    if recent_events:
        lines.append("## Recent Activity (your previous sessions)")
        for event in recent_events[:15]:
            ts = str(event.get("created_at", ""))[:16]
            tool = event.get("tool_name", "")
            content = str(event.get("content", ""))[:200]
            event_type = event.get("event_type", "")
            if tool:
                lines.append(f"- [{ts}] {tool}: {content}")
            else:
                lines.append(f"- [{ts}] ({event_type}) {content}")
        lines.append("")

    return "\n".join(lines)


def stream_user_message(cfg: dict, state: dict, prompt_text: str):
    """Push the user's prompt to the history store."""
    if not cfg["workspace_id"] or not cfg["history_store_id"]:
        return
    if not prompt_text or not prompt_text.strip():
        return
    try:
        with get_client() as client:
            client.push_event(
                workspace_id=cfg["workspace_id"],
                store_id=cfg["history_store_id"],
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

    # Read hook payload from stdin
    hook_data = get_stdin_data()
    prompt_text = hook_data.get("prompt", hook_data.get("userPrompt", ""))
    hook_session_id = hook_data.get("session_id", "")

    cfg = get_config()
    state = load_state()
    session_id = hook_session_id or state.get("session_id", "")

    # --- Always stream the user message ---
    stream_user_message(cfg, state, prompt_text)

    # --- Injection (skip if disabled) ---
    if cfg.get("inject_context", "true").lower() in ("false", "0", "no", "off"):
        return

    session_state = load_injection_state()
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
        cache = load_cache()
        persona = state.get("persona", "")
        if not persona and cache and cache.get("profile"):
            persona = str(cache["profile"].get("description", ""))
        recent_events = cache.get("recent_events", []) if cache else []
        context = build_fallback_context(
            cfg["agent_name"],
            persona,
            recent_events,
        )
        # Increment prompt_num locally
        session_state["prompt_num"] = session_state.get("prompt_num", 0) + 1
        save_injection_state(session_state)

    # --- Append pending escalations from OCTOPUS_NOTIFICATIONS_DIR (if any) ---
    escalations = load_escalations()
    if escalations:
        context += "\n\n## Escalations\n" + "\n".join(escalations)

    # Output the context for injection
    output = {"additionalContext": context}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
