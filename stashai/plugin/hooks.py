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

from stashai.plugin.event import HookEvent
from stashai.plugin.scope import cwd_in_scope, repo_transcript_hook_enabled
from stashai.plugin.stash_client import StashClient
from stashai.plugin.state import read_stats, record_tool_use
from stashai.plugin.summarize import summarize_tool_use


def _short_circuit(cfg: dict, event: HookEvent | None) -> bool:
    if not cfg.get("workspace_id"):
        return True
    cwd = getattr(event, "cwd", None) if event is not None else None
    if not repo_transcript_hook_enabled(cwd):
        return True
    return not cwd_in_scope(cwd)


# --- Prompt streaming ---

def stream_user_message(
    client: StashClient, cfg: dict, state: dict, prompt_text: str,
    event: HookEvent | None = None,
) -> None:
    if _short_circuit(cfg, event):
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
    client: StashClient, cfg: dict, state: dict, event: HookEvent,
    data_dir: Path | None = None,
) -> None:
    if _short_circuit(cfg, event):
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
    client: StashClient, cfg: dict, state: dict, event: HookEvent,
) -> None:
    """Push the final assistant text for a turn. Call from per-turn Stop /
    afterAgentResponse / AfterAgent hooks. Never emits session_end — the
    session is still live."""
    if _short_circuit(cfg, event):
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
    client: StashClient, cfg: dict, state: dict, event: HookEvent,
) -> None:
    """Push the session_end summary AND upload the full transcript (.jsonl)
    if the agent exposed one. Call ONCE per conversation from SessionEnd /
    session.deleted hooks. The upload uses a 60s per-request timeout (the
    default StashClient timeout is 2s, fine for small events but way too
    short for a 50MB transcript).
    """
    if _short_circuit(cfg, event):
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

    tp = getattr(event, "transcript_path", "") or ""
    sid = state.get("session_id", "") or ""
    if not tp or not sid.strip():
        return
    path = Path(tp)
    if not path.is_file():
        return
    try:
        client.upload_transcript(
            workspace_id=cfg["workspace_id"],
            session_id=sid,
            transcript_path=path,
            agent_name=cfg["agent_name"],
            cwd=event.cwd,
        )
    except Exception:
        pass
