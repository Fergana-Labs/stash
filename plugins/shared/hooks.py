"""Agent-agnostic hook logic. Each per-plugin on_*.py script is a thin wrapper
that (1) reads agent-specific stdin, (2) adapts to a HookEvent, (3) calls into
here. Nothing in this file knows about any specific agent's payload shape.

Every function swallows network exceptions so a flaky backend never kills a
user's coding session.

Naming: `stream_assistant_message` fires at every turn end (assistant finished
talking). `stream_session_end` fires once when the whole conversation ends.
Never call `stream_session_end` from a per-turn hook — you'll emit a bogus
`session_end` event on every turn and break session correlation downstream.
"""

from __future__ import annotations

from pathlib import Path

from event import HookEvent
from octopus_client import OctopusClient
from state import read_stats, record_tool_use
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
    data_dir: Path | None = None,
) -> None:
    if not cfg.get("workspace_id"):
        return
    if not event.tool_name:
        return

    content, metadata = summarize_tool_use(
        event.tool_name, event.tool_input, event.tool_response,
    )
    metadata["cwd"] = event.cwd

    if data_dir is not None:
        record_tool_use(data_dir, event.tool_name, metadata.get("file_path"))

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


# --- Turn end (assistant finished responding; session still open) ---

def stream_assistant_message(
    client: OctopusClient, cfg: dict, state: dict, event: HookEvent,
) -> None:
    """Push the final assistant text for a turn. Call from per-turn Stop /
    afterAgentResponse / AfterAgent hooks. Never emits session_end — the
    session is still live."""
    if not cfg.get("workspace_id"):
        return
    if not event.last_assistant_message:
        return
    try:
        client.push_event(
            workspace_id=cfg["workspace_id"],
            agent_name=cfg["agent_name"],
            event_type="assistant_message",
            content=event.last_assistant_message[:4000],
            session_id=state.get("session_id", ""),
            client=cfg.get("client") or None,
        )
    except Exception:
        pass


# --- Session end (conversation over) ---

def stream_session_end(
    client: OctopusClient, cfg: dict, state: dict, event: HookEvent,
) -> None:
    """Push the final session_end summary. Call ONCE per conversation from
    SessionEnd / session.deleted hooks. Stats come from the running counter
    maintained by stream_tool_use — no transcript reads, no timeout risk."""
    if not cfg.get("workspace_id"):
        return

    stats = read_stats(state)
    tool_count = stats["tool_count"]
    files_changed = stats["files_changed"]
    tools_used = stats["tools_used"]

    parts = ["Session ended."]
    if tool_count:
        parts.append(f"{tool_count} tool uses.")
    if files_changed:
        parts.append(f"{len(files_changed)} files changed.")

    try:
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
