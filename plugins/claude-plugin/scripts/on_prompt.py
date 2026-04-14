#!/usr/bin/env python3
"""UserPromptSubmit hook: stream user message + inject recent-activity context.

1. Always streams the user's prompt to the Octopus history store
2. Injects agent identity + recent activity from local cache (unless inject_context=false)
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    get_config, get_client, get_stdin_data, is_configured,
    load_state, load_cache,
    load_escalations,
)


def build_context(
    agent_name: str,
    description: str,
    recent_events: list[dict],
) -> str:
    """Build identity + recent-activity context from the local cache."""
    lines = []
    lines.append("## Agent Identity")
    lines.append(f"You are **{agent_name}**, a Octopus agent.")
    if description:
        lines.append(description)
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

    hook_data = get_stdin_data()
    prompt_text = hook_data.get("prompt", hook_data.get("userPrompt", ""))

    cfg = get_config()
    state = load_state()

    stream_user_message(cfg, state, prompt_text)

    if cfg.get("inject_context", "true").lower() in ("false", "0", "no", "off"):
        return

    cache = load_cache()
    description = ""
    if cache and cache.get("profile"):
        description = str(cache["profile"].get("description", ""))
    recent_events = cache.get("recent_events", []) if cache else []
    context = build_context(cfg["agent_name"], description, recent_events)

    escalations = load_escalations()
    if escalations:
        context += escalations

    output = {"additionalContext": context}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
