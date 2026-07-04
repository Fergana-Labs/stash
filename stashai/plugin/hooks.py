"""Agent-agnostic hook logic. Each per-plugin on_*.py script is a thin wrapper
that (1) reads agent-specific stdin, (2) adapts to a HookEvent, (3) calls into
here. Nothing in this file knows about any specific agent's payload shape.

Every function swallows network exceptions so a flaky backend never kills a
user's coding session.

Streaming is a global, single-player gate: a session streams iff the plugin is
configured (api_key + agent_name) and streaming has not been globally stopped.
There is no `.stash` manifest and no cwd/path-based scope. Sessions upload to
the user's own scope; the backend assigns the default session folder unless the
user pinned one.

Naming: `stream_assistant_message` fires at every turn end (assistant finished
talking). `stream_session_end` fires once when the whole conversation ends.
Never call `stream_session_end` from a per-turn hook — you'll emit a bogus
`session_end` event on every turn and break session correlation downstream.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from stashai.plugin.event import HookEvent
from stashai.plugin.scope import streaming_enabled
from stashai.plugin.session_upload import spawn_session_upload
from stashai.plugin.stash_client import StashClient
from stashai.plugin.state import read_stats, record_tool_use, save_state
from stashai.plugin.summarize import summarize_tool_use
from stashai.plugin.upload_status import (
    read_upload_status,
    record_upload_failure,
    record_upload_success,
)

_CONFIG_FILE = Path.home() / ".stash" / "config.json"

_CLIENT_TO_AGENT = {
    "claude_code": "claude",
    "cursor": "cursor",
    "codex_cli": "codex",
    "opencode": "opencode",
}

_UPLOAD_WARNING_SESSION_KEY = "upload_warning_session_id"
_UPLOAD_WARNING_MESSAGE = (
    "Stash uploads are failing; this conversation may not be visible to your team. "
    "Run `stash status` for details."
)
_UPLOADS_DISABLED_WARNING_SESSION_KEY = "uploads_disabled_warning_session_id"
_UPLOADS_DISABLED_WARNING_MESSAGE = (
    "Stash isn't set up on this machine yet. "
    "Run `stash connect` to finish setup."
)
_ENDED_SESSION_ID_KEY = "ended_session_id"
_YELLOW = "\033[33m"
_RESET = "\033[0m"
_METADATA_EXTRA_KEYS = ("model", "permission_mode", "cursor_version", "generation_id")


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


def _short_circuit(cfg: dict) -> bool:
    """Return True when this session should NOT stream.

    Streams by default whenever the plugin is configured and streaming hasn't
    been globally stopped. Only skips when the agent is disabled, the plugin is
    unconfigured, or the user ran `stash stop`.
    """
    if not _is_agent_enabled(cfg):
        return True
    if not cfg.get("agent_name"):
        return True
    return not streaming_enabled()


def _event_metadata(event: HookEvent | None, base: dict | None = None) -> dict:
    metadata = dict(base or {})
    if event is None:
        return metadata

    for key in _METADATA_EXTRA_KEYS:
        value = event.extras.get(key)
        if isinstance(value, str) and value:
            metadata[key] = value
    return metadata


def uploads_enabled(cfg: dict) -> bool:
    if not cfg.get("api_key") or not cfg.get("agent_name"):
        return False
    return not _short_circuit(cfg)


def uploads_disabled_warning(
    cfg: dict,
    state: dict,
    event: HookEvent | None,
    data_dir: Path,
) -> str | None:
    """Return the once-per-session warning when the plugin isn't set up here."""
    if uploads_enabled(cfg):
        return None
    session_id = getattr(event, "session_id", "") if event is not None else ""
    if not session_id:
        return None
    if state.get(_UPLOADS_DISABLED_WARNING_SESSION_KEY) == session_id:
        return None
    if shutil.which("stash") is None:
        return None
    if cfg.get("api_key") and cfg.get("agent_name"):
        return None

    state[_UPLOADS_DISABLED_WARNING_SESSION_KEY] = session_id
    save_state(data_dir, state)
    return _UPLOADS_DISABLED_WARNING_MESSAGE


# --- Session lifecycle ---

_SESSION_STATE_KEYS = (
    "session_row_id",
    "session_url",
    "uploaded_session_id",
    "transcript_path",
    "cwd",
    _ENDED_SESSION_ID_KEY,
)


def reset_session_record_state(state: dict) -> None:
    """Clear stale upload metadata before a new session is recorded."""
    for key in _SESSION_STATE_KEYS:
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


def create_session_record(
    client: StashClient,
    cfg: dict,
    state: dict,
    event: HookEvent,
    data_dir: Path | None = None,
) -> str | None:
    """Create the session row shared by all agent plugins.

    The hook must stay best-effort: backend/network failures should never
    interrupt the user's coding agent.
    """
    if _short_circuit(cfg):
        return None

    sid = event.session_id or state.get("session_id", "")
    if not sid:
        return None
    if event.cwd:
        state["cwd"] = event.cwd

    if state.get("session_row_id") and state.get("uploaded_session_id") == sid:
        return state.get("session_url")

    try:
        session = client.create_session(
            session_id=sid,
            agent_name=cfg["agent_name"],
            cwd=event.cwd,
            files_touched=read_stats(state)["files_touched"],
            session_folder_id=cfg.get("session_folder_id") or None,
        )
    except Exception as e:
        record_upload_failure(data_dir, "session", e)
        return None
    record_upload_success(data_dir, "session")

    state["session_row_id"] = str(session["id"])
    # The record link points at the web app (PUBLIC_URL), not the API host, so
    # use the canonical app_url the backend returns rather than building one off
    # api_endpoint.
    state["session_url"] = session["app_url"]
    state["uploaded_session_id"] = sid
    state["cwd"] = event.cwd or state.get("cwd", "")
    remember_transcript_path(state, event)
    if data_dir is not None:
        save_state(data_dir, state)
    return state["session_url"] or None


def finalize_session_upload(
    client: StashClient,
    cfg: dict,
    state: dict,
    event: HookEvent,
    data_dir: Path | None = None,
) -> bool:
    """Start the detached artifact upload process for a session."""
    if not event.cwd and state.get("cwd"):
        event.cwd = state["cwd"]

    if _short_circuit(cfg):
        return False

    sid = event.session_id or state.get("session_id", "")
    if not sid:
        return False

    remember_transcript_path(state, event)

    session_row_id = state.get("session_row_id", "")
    if not session_row_id:
        create_session_record(client, cfg, state, event, data_dir)
        session_row_id = state.get("session_row_id", "")
    if not session_row_id:
        return False

    stats = read_stats(state)
    transcript_path = event.transcript_path or state.get("transcript_path", "")
    cwd = event.cwd or state.get("cwd", "")
    if not cwd:
        cwd = ""

    spawned = spawn_session_upload(
        session_row_id=session_row_id,
        transcript_path=transcript_path,
        cwd=cwd,
        files_touched=stats["files_touched"],
        session_id=sid,
        agent_name=cfg["agent_name"],
        base_url=cfg["api_endpoint"],
        api_key=cfg["api_key"],
        data_dir=data_dir,
    )
    if data_dir is not None:
        save_state(data_dir, state)
    return spawned


# --- Prompt streaming ---

def stream_user_message(
    client: StashClient, cfg: dict, state: dict, prompt_text: str,
    event: HookEvent | None = None,
) -> None:
    if _short_circuit(cfg):
        return
    if not prompt_text or not prompt_text.strip():
        return
    sid = (event.session_id if event is not None else "") or state.get("session_id", "")
    if not sid:
        return
    try:
        client.push_event(
            agent_name=cfg["agent_name"],
            event_type="user_message",
            content=prompt_text,
            session_id=sid,
            session_folder_id=cfg.get("session_folder_id") or None,
            metadata=_event_metadata(event),
            client=cfg.get("client") or None,
        )
    except Exception:
        pass


# --- Tool use streaming ---

def stream_tool_use(
    client: StashClient, cfg: dict, state: dict, event: HookEvent,
    data_dir: Path | None = None,
) -> None:
    if _short_circuit(cfg):
        return
    if not event.tool_name:
        return
    sid = event.session_id or state.get("session_id", "")
    if not sid:
        return

    content, metadata = summarize_tool_use(
        event.tool_name, event.tool_input, event.tool_response,
    )
    metadata = _event_metadata(event, metadata)
    metadata["cwd"] = event.cwd

    if data_dir is not None:
        record_tool_use(data_dir, event.tool_name, metadata.get("file_path"))

    try:
        client.push_event(
            agent_name=cfg["agent_name"],
            event_type="tool_use",
            content=content,
            session_id=sid,
            session_folder_id=cfg.get("session_folder_id") or None,
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
    if _short_circuit(cfg):
        return
    if not event.last_assistant_message:
        return
    sid = event.session_id or state.get("session_id", "")
    if not sid:
        return
    try:
        client.push_event(
            agent_name=cfg["agent_name"],
            event_type="assistant_message",
            content=event.last_assistant_message,
            session_id=sid,
            session_folder_id=cfg.get("session_folder_id") or None,
            metadata=_event_metadata(event),
            client=cfg.get("client") or None,
        )
    except Exception:
        pass


def upload_health_warning(
    cfg: dict,
    state: dict,
    event: HookEvent,
    data_dir: Path,
) -> str | None:
    """Return the once-per-session local upload failure warning, if needed."""
    if _short_circuit(cfg):
        return None

    session_id = event.session_id or state.get("session_id", "")
    if not session_id:
        return None
    if state.get(_UPLOAD_WARNING_SESSION_KEY) == session_id:
        return None

    status = read_upload_status(data_dir)
    if status.get("health") != "failing":
        return None

    state[_UPLOAD_WARNING_SESSION_KEY] = session_id
    save_state(data_dir, state)
    return _UPLOAD_WARNING_MESSAGE


def color_upload_health_warning(message: str) -> str:
    return f"{_YELLOW}{message}{_RESET}"


# --- Session end (conversation over) ---

def stream_session_end(
    client: StashClient, cfg: dict, state: dict, event: HookEvent,
) -> str | None:
    """Push the session_end event and upload transcript.

    Returns the stash URL if one was created, None otherwise.
    """
    if not event.cwd and state.get("cwd"):
        event.cwd = state["cwd"]

    if _short_circuit(cfg):
        return None

    sid = event.session_id or state.get("session_id", "")
    if not sid.strip():
        return None
    if state.get(_ENDED_SESSION_ID_KEY) == sid:
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
            agent_name=cfg["agent_name"],
            event_type="session_end",
            content=" ".join(parts),
            session_id=sid,
            session_folder_id=cfg.get("session_folder_id") or None,
            metadata=_event_metadata(
                event,
                {
                    "cwd": event.cwd,
                    "tool_count": tool_count,
                    "files_touched": files_touched,
                    "tools_used": tools_used,
                },
            ),
            client=cfg.get("client") or None,
        )
    except Exception:
        pass
    else:
        state[_ENDED_SESSION_ID_KEY] = sid

    tp = getattr(event, "transcript_path", "") or ""
    if not tp:
        return None
    path = Path(tp)
    if not path.is_file():
        return None

    session_folder_id = cfg.get("session_folder_id") or None
    try:
        client.upload_transcript(
            session_id=sid,
            transcript_path=path,
            agent_name=cfg["agent_name"],
            cwd=event.cwd,
            session_folder_id=session_folder_id,
        )
    except Exception:
        pass

    subagents_dir = path.parent / path.stem / "subagents"
    if subagents_dir.is_dir():
        for sa_jsonl in subagents_dir.glob("agent-*.jsonl"):
            try:
                client.upload_transcript(
                    session_id=sa_jsonl.stem,
                    transcript_path=sa_jsonl,
                    agent_name="claude-subagent",
                    cwd=event.cwd,
                    session_folder_id=session_folder_id,
                )
            except Exception:
                pass

    return None
