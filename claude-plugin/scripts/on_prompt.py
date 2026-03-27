#!/usr/bin/env python3
"""UserPromptSubmit hook: inject agent persona and memory context."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, get_client, is_configured, load_state, load_cache, save_cache


def format_event(event: dict) -> str:
    ts = event.get("created_at", "")[:16]  # trim to minute
    event_type = event.get("event_type", "")
    tool = event.get("tool_name", "")
    content = event.get("content", "")[:200]
    prefix = f"[{ts}]"
    if tool:
        return f"{prefix} {tool}: {content}"
    return f"{prefix} ({event_type}) {content}"


def build_context() -> str | None:
    """Build the persona + memory context string."""
    cfg = get_config()
    if not cfg["agent_name"]:
        return None

    state = load_state()
    cache = load_cache()

    # If cache is stale, try a quick refresh
    if cache is None and cfg["workspace_id"] and cfg["history_store_id"]:
        try:
            with get_client() as client:
                profile = client.whoami()
                recent_events = client.query_events(
                    cfg["workspace_id"], cfg["history_store_id"], limit=20,
                )
                save_cache(profile, recent_events)
                cache = {"profile": profile, "recent_events": recent_events}
        except Exception:
            pass

    # Build persona section
    persona = state.get("persona", "")
    if not persona and cache and cache.get("profile"):
        persona = cache["profile"].get("description", "")

    lines = []
    lines.append(f"## Agent Identity")
    lines.append(f"You are **{cfg['agent_name']}**, a Boozle agent.")
    if persona:
        lines.append(f"{persona}")
    lines.append("")

    # Build recent activity section
    if cache and cache.get("recent_events"):
        lines.append("## Recent Activity (your previous sessions)")
        for event in cache["recent_events"][:15]:
            lines.append(f"- {format_event(event)}")
        lines.append("")

    return "\n".join(lines)


def main():
    if not is_configured():
        return

    context = build_context()
    if context:
        print(json.dumps({"userPromptContent": context}))


if __name__ == "__main__":
    main()
