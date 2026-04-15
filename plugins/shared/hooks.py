"""Agent-agnostic hook logic. Each per-plugin on_*.py script is a thin wrapper
that (1) reads agent-specific stdin, (2) adapts to a HookEvent, (3) calls into
here. Nothing in this file knows about any specific agent's payload shape.

Every function swallows network exceptions so a flaky backend never kills a
user's coding session.
"""

from __future__ import annotations

import json

from event import HookEvent
from octopus_client import OctopusClient
from summarize import summarize_tool_use


# --- Prompt streaming ---

def stream_user_message(client: OctopusClient, cfg: dict, state: dict, prompt_text: str) -> None:
    if not cfg.get("workspace_id"):
        return
    if not prompt_text or not prompt_text.strip():
        return
    try:
        client.push_event(
            workspace_id=cfg["workspace_id"],
            agent_name=cfg["agent_name"],
            event_type="user_message",
            content=prompt_text[:2000],
            session_id=state.get("session_id", ""),
            client=cfg.get("client") or None,
        )
    except Exception:
        pass


# --- Tool use streaming ---

def stream_tool_use(
    client: OctopusClient, cfg: dict, state: dict, event: HookEvent,
) -> None:
    if not cfg.get("workspace_id"):
        return
    if not event.tool_name:
        return

    content, metadata = summarize_tool_use(
        event.tool_name, event.tool_input, event.tool_response,
    )
    metadata["cwd"] = event.cwd

    try:
        client.push_event(
            workspace_id=cfg["workspace_id"],
            agent_name=cfg["agent_name"],
            event_type="tool_use",
            content=content,
            session_id=state.get("session_id", ""),
            tool_name=event.tool_name,
            metadata=metadata,
            client=cfg.get("client") or None,
        )
    except Exception:
        pass


# --- Stop / session end ---

def count_transcript_stats(transcript_path: str) -> dict:
    """Count tool uses + files changed from a JSONL transcript.

    Only supports Claude Code's transcript format today; other agents may add
    their own or pass '' to skip. Gracefully returns empty stats on any error.
    """
    stats = {"tool_count": 0, "files_changed": set(), "tools_used": set()}
    if not transcript_path:
        return {"tool_count": 0, "files_changed": [], "tools_used": []}

    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("type") != "tool_use":
                    continue
                stats["tool_count"] += 1
                name = entry.get("name", "")
                stats["tools_used"].add(name)
                tin = entry.get("input", {})
                if isinstance(tin, dict):
                    fp = tin.get("file_path", "")
                    if fp and name in ("Edit", "Write"):
                        stats["files_changed"].add(fp)
    except Exception:
        pass

    stats["files_changed"] = list(stats["files_changed"])
    stats["tools_used"] = list(stats["tools_used"])
    return stats


def stream_stop(
    client: OctopusClient, cfg: dict, state: dict, event: HookEvent,
) -> None:
    if not cfg.get("workspace_id"):
        return

    try:
        if event.last_assistant_message:
            client.push_event(
                workspace_id=cfg["workspace_id"],
                agent_name=cfg["agent_name"],
                event_type="assistant_message",
                content=event.last_assistant_message[:4000],
                session_id=state.get("session_id", ""),
                client=cfg.get("client") or None,
            )

        stats = count_transcript_stats(event.transcript_path)
        tool_count = stats.get("tool_count", 0)
        files_changed = stats.get("files_changed", [])
        tools_used = stats.get("tools_used", [])

        parts = ["Session ended."]
        if tool_count:
            parts.append(f"{tool_count} tool uses.")
        if files_changed:
            parts.append(f"{len(files_changed)} files changed.")

        client.push_event(
            workspace_id=cfg["workspace_id"],
            agent_name=cfg["agent_name"],
            event_type="session_end",
            content=" ".join(parts),
            session_id=state.get("session_id", ""),
            metadata={
                "cwd": event.cwd,
                "tool_count": tool_count,
                "files_changed": files_changed,
                "tools_used": tools_used,
            },
            client=cfg.get("client") or None,
        )
    except Exception:
        pass
