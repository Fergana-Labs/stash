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

import json
import os

from event import HookEvent
from octopus_client import OctopusClient
from summarize import summarize_tool_use

# Read at most this many bytes from the tail of a transcript when computing
# session_end stats. Long Claude sessions can produce hundreds of MB of JSONL;
# parsing all of it past Codex's 5s hook timeout kills the session_end push
# AND the curate spawn that follows. Tail-only is best-effort: stats undercount
# on huge sessions, but the load-bearing curate trigger still fires.
_TRANSCRIPT_TAIL_BYTES = 5 * 1024 * 1024


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

def count_transcript_stats(transcript_path: str) -> dict:
    """Count tool uses + files changed from a Claude Code JSONL transcript.

    Claude-specific format (`{"type":"tool_use", "name":..., "input":...}`).
    Non-Claude transcripts produce zero counts — the caller should gate by
    `cfg.client == "claude_code"` to avoid reading opaque files.

    Reads at most _TRANSCRIPT_TAIL_BYTES from the end of the file so the hook
    completes inside the host's timeout even on multi-hundred-MB transcripts.
    """
    stats = {"tool_count": 0, "files_changed": set(), "tools_used": set(), "truncated": False}
    if not transcript_path:
        return _finalize_stats(stats)

    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as f:
            if size > _TRANSCRIPT_TAIL_BYTES:
                f.seek(size - _TRANSCRIPT_TAIL_BYTES)
                f.readline()  # discard partial first line
                stats["truncated"] = True
            for raw in f:
                try:
                    entry = json.loads(raw)
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

    return _finalize_stats(stats)


def _finalize_stats(stats: dict) -> dict:
    return {
        "tool_count": stats["tool_count"],
        "files_changed": list(stats["files_changed"]) if isinstance(stats["files_changed"], set) else stats["files_changed"],
        "tools_used": list(stats["tools_used"]) if isinstance(stats["tools_used"], set) else stats["tools_used"],
        "truncated": stats.get("truncated", False),
    }


def stream_session_end(
    client: OctopusClient, cfg: dict, state: dict, event: HookEvent,
) -> None:
    """Push the final session_end summary. Call ONCE per conversation from
    SessionEnd / session.deleted hooks. Claude plugins optionally include
    transcript-derived stats."""
    if not cfg.get("workspace_id"):
        return

    if cfg.get("client") == "claude_code" and event.transcript_path:
        stats = count_transcript_stats(event.transcript_path)
    else:
        stats = {"tool_count": 0, "files_changed": [], "tools_used": [], "truncated": False}

    tool_count = stats["tool_count"]
    files_changed = stats["files_changed"]
    tools_used = stats["tools_used"]
    truncated = stats.get("truncated", False)

    parts = ["Session ended."]
    if tool_count:
        suffix = "+" if truncated else ""
        parts.append(f"{tool_count}{suffix} tool uses.")
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
                "stats_truncated": truncated,
            },
            client=cfg.get("client") or None,
        )
    except Exception:
        pass
