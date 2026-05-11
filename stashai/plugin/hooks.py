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

from stashai.plugin.stash_upload import spawn_stash_upload
from stashai.plugin.event import HookEvent
from stashai.plugin.scope import cwd_in_scope, find_manifest
from stashai.plugin.stash_client import StashClient
from stashai.plugin.state import read_stats, record_tool_use, save_state
from stashai.plugin.summarize import summarize_tool_use

_CONFIG_FILE = Path.home() / ".stash" / "config.json"

_CLIENT_TO_AGENT = {
    "claude_code": "claude",
    "cursor": "cursor",
    "codex_cli": "codex",
    "opencode": "opencode",
}


def _read_user_config() -> dict:
    if not _CONFIG_FILE.exists():
        return {}
    try:
        import json
        return json.loads(_CONFIG_FILE.read_text())
    except Exception:
        return {}


def _is_agent_enabled(cfg: dict) -> bool:
    data = _read_user_config()
    enabled = data.get("enabled_agents")
    if not isinstance(enabled, list):
        return True
    client = cfg.get("client", "")
    if not client:
        return True
    canonical = _CLIENT_TO_AGENT.get(client, client)
    return canonical in enabled


def _is_stopped(workspace_id: str) -> bool:
    stopped = _read_user_config().get("stopped_streaming")
    return isinstance(stopped, list) and workspace_id in stopped


def _resolve_workspace(cfg: dict, event: HookEvent | None) -> str | None:
    """Return workspace_id if this session should attempt streaming, else None."""
    cwd = getattr(event, "cwd", None) if event is not None else None

    if cfg.get("workspace_id"):
        if not cwd_in_scope(cwd):
            return None
        return cfg["workspace_id"]

    manifest = find_manifest(cwd) if cwd else None
    if not manifest:
        return None
    return manifest.get("workspace_id") or None


def _short_circuit(cfg: dict, event: HookEvent | None) -> tuple[bool, str | None]:
    """Return (should_skip, workspace_id).

    Streams by default to any workspace with a manifest. Only skips if the
    user explicitly ran `stash stop`.
    """
    if not _is_agent_enabled(cfg):
        return True, None

    workspace_id = _resolve_workspace(cfg, event)
    if not workspace_id:
        return True, None

    if _is_stopped(workspace_id):
        return True, None

    return False, workspace_id


# --- Session stash lifecycle ---

_STASH_STATE_KEYS = (
    "stash_id",
    "stash_url",
    "stash_session_id",
    "stash_workspace_id",
    "transcript_path",
    "cwd",
)


def reset_session_stash_state(state: dict) -> None:
    """Clear stale bundle metadata before a new session is recorded."""
    for key in _STASH_STATE_KEYS:
        state.pop(key, None)


def remember_transcript_path(
    state: dict, event: HookEvent, data_dir: Path | None = None,
) -> None:
    """Persist the newest transcript path an agent exposes for this session."""
    if not event.transcript_path:
        return
    state["transcript_path"] = event.transcript_path
    if data_dir is not None:
        save_state(data_dir, state)


def create_session_stash(
    client: StashClient,
    cfg: dict,
    state: dict,
    event: HookEvent,
    data_dir: Path | None = None,
) -> str | None:
    """Create the public session bundle row shared by all agent plugins.

    The hook must stay best-effort: backend/network failures should never
    interrupt the user's coding agent.
    """
    skip, workspace_id = _short_circuit(cfg, event)
    if skip:
        return None

    sid = event.session_id or state.get("session_id", "")
    if not sid:
        return None
    if event.cwd:
        state["cwd"] = event.cwd

    if state.get("stash_id") and state.get("stash_session_id") == sid:
        return state.get("stash_url")

    try:
        stash = client.create_stash(
            workspace_id=workspace_id,
            session_id=sid,
            agent_name=cfg["agent_name"],
            cwd=event.cwd,
            files_touched=read_stats(state)["files_touched"],
        )
    except Exception:
        return None

    state["stash_id"] = str(stash["id"])
    state["stash_url"] = stash.get("url", "")
    state["stash_session_id"] = sid
    state["stash_workspace_id"] = workspace_id
    state["cwd"] = event.cwd or state.get("cwd", "")
    remember_transcript_path(state, event)
    if data_dir is not None:
        save_state(data_dir, state)
    return state["stash_url"] or None


def finalize_session_stash(
    client: StashClient,
    cfg: dict,
    state: dict,
    event: HookEvent,
    data_dir: Path | None = None,
) -> bool:
    """Start the detached upload + summary generation process for a session."""
    if not event.cwd and state.get("cwd"):
        event.cwd = state["cwd"]

    skip, workspace_id = _short_circuit(cfg, event)
    if skip:
        return False

    sid = event.session_id or state.get("session_id", "")
    if not sid:
        return False

    remember_transcript_path(state, event)

    stash_id = state.get("stash_id", "")
    if not stash_id:
        create_session_stash(client, cfg, state, event, data_dir)
        stash_id = state.get("stash_id", "")
    if not stash_id:
        return False

    stats = read_stats(state)
    transcript_path = event.transcript_path or state.get("transcript_path", "")
    cwd = event.cwd or state.get("cwd", "")
    if not cwd:
        cwd = ""

    spawned = spawn_stash_upload(
        stash_id=stash_id,
        transcript_path=transcript_path,
        cwd=cwd,
        files_touched=stats["files_touched"],
        workspace_id=workspace_id,
        session_id=sid,
        agent_name=cfg["agent_name"],
        base_url=cfg["api_endpoint"],
        api_key=cfg["api_key"],
    )
    if data_dir is not None:
        save_state(data_dir, state)
    return spawned


# --- Prompt streaming ---

def stream_user_message(
    client: StashClient, cfg: dict, state: dict, prompt_text: str,
    event: HookEvent | None = None,
) -> None:
    skip, workspace_id = _short_circuit(cfg, event)
    if skip:
        return
    if not prompt_text or not prompt_text.strip():
        return
    try:
        client.push_event(
            workspace_id=workspace_id,
            agent_name=cfg["agent_name"],
            event_type="user_message",
            content=prompt_text,
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
    skip, workspace_id = _short_circuit(cfg, event)
    if skip:
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
            workspace_id=workspace_id,
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
    skip, workspace_id = _short_circuit(cfg, event)
    if skip:
        return
    if not event.last_assistant_message:
        return
    try:
        client.push_event(
            workspace_id=workspace_id,
            agent_name=cfg["agent_name"],
            event_type="assistant_message",
            content=event.last_assistant_message,
            session_id=state.get("session_id", ""),
            client=cfg.get("client") or None,
        )
    except Exception:
        pass


# --- Session end (conversation over) ---

def stream_session_end(
    client: StashClient, cfg: dict, state: dict, event: HookEvent,
) -> str | None:
    """Push the session_end summary and upload transcript.

    Returns the stash URL if one was created, None otherwise.
    """
    if not event.cwd and state.get("cwd"):
        event.cwd = state["cwd"]

    skip, workspace_id = _short_circuit(cfg, event)
    if skip:
        return None

    stats = read_stats(state)
    tool_count = stats["tool_count"]
    files_touched = stats["files_touched"]
    tools_used = stats["tools_used"]

    parts = ["Session ended."]
    if tool_count:
        parts.append(f"{tool_count} tool uses.")
    if files_touched:
        parts.append(f"{len(files_touched)} files touched.")

    try:
        client.push_event(
            workspace_id=workspace_id,
            agent_name=cfg["agent_name"],
            event_type="session_end",
            content=" ".join(parts),
            session_id=state.get("session_id", ""),
            metadata={
                "cwd": event.cwd,
                "tool_count": tool_count,
                "files_touched": files_touched,
                "tools_used": tools_used,
            },
            client=cfg.get("client") or None,
        )
    except Exception:
        pass

    tp = getattr(event, "transcript_path", "") or ""
    sid = state.get("session_id", "") or ""
    if not tp or not sid.strip():
        return None
    path = Path(tp)
    if not path.is_file():
        return None

    try:
        client.upload_transcript(
            workspace_id=workspace_id,
            session_id=sid,
            transcript_path=path,
            agent_name=cfg["agent_name"],
            cwd=event.cwd,
        )
    except Exception:
        pass

    subagents_dir = path.parent / path.stem / "subagents"
    if subagents_dir.is_dir():
        for sa_jsonl in subagents_dir.glob("agent-*.jsonl"):
            try:
                client.upload_transcript(
                    workspace_id=workspace_id,
                    session_id=sa_jsonl.stem,
                    transcript_path=sa_jsonl,
                    agent_name="claude-subagent",
                    cwd=event.cwd,
                )
            except Exception:
                pass

    return None
