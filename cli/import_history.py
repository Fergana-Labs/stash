"""Discover and import historical conversations from coding agents.

Supports Claude Code, Cursor, and Codex. Each agent stores conversations as
.jsonl files in predictable locations under ~/.<agent>/. We discover them,
extract lightweight metadata (session_id, cwd, timestamp, size), and upload
them as transcript blobs + summary events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CURSOR_PROJECTS_DIR = Path.home() / ".cursor" / "projects"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


@dataclass
class ConversationInfo:
    agent: str
    session_id: str
    path: Path
    cwd: str
    timestamp: datetime
    size_bytes: int
    user_messages: int = 0
    extras: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Claude Code: ~/.claude/projects/<project-dir>/<uuid>.jsonl
# First line is {type: "permission-mode", sessionId: "..."}.
# Subsequent lines have {type, timestamp, cwd, sessionId}.
# ---------------------------------------------------------------------------


def _discover_claude() -> list[ConversationInfo]:
    if not CLAUDE_PROJECTS_DIR.is_dir():
        return []

    results = []
    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            info = _parse_claude_meta(jsonl)
            if info:
                results.append(info)
    return results


def _parse_claude_meta(path: Path) -> ConversationInfo | None:
    size = path.stat().st_size
    if size < 10:
        return None

    session_id = ""
    cwd = ""
    timestamp = None
    user_count = 0

    with open(path) as f:
        for i, raw in enumerate(f):
            if i > 50:
                break
            try:
                line = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if not session_id:
                session_id = line.get("sessionId", "")
            if not cwd and line.get("cwd"):
                cwd = line["cwd"]
            if not timestamp and line.get("timestamp"):
                timestamp = _parse_iso(line["timestamp"])
            if line.get("type") == "user":
                user_count += 1
                if user_count >= 3:
                    break

    if not session_id:
        session_id = path.stem

    if not timestamp:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    return ConversationInfo(
        agent="claude",
        session_id=session_id,
        path=path,
        cwd=cwd,
        timestamp=timestamp,
        size_bytes=size,
        user_messages=user_count,
    )


# ---------------------------------------------------------------------------
# Cursor: ~/.cursor/projects/<project-dir>/agent-transcripts/<id>/<id>.jsonl
# Lines are {role: "user"/"assistant", message: {content: [...]}}
# ---------------------------------------------------------------------------


def _discover_cursor() -> list[ConversationInfo]:
    if not CURSOR_PROJECTS_DIR.is_dir():
        return []

    results = []
    for project_dir in CURSOR_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        transcripts_dir = project_dir / "agent-transcripts"
        if not transcripts_dir.is_dir():
            continue
        for session_dir in transcripts_dir.iterdir():
            if not session_dir.is_dir():
                continue
            for jsonl in session_dir.glob("*.jsonl"):
                info = _parse_cursor_meta(jsonl, project_dir.name)
                if info:
                    results.append(info)
    return results


def _parse_cursor_meta(path: Path, project_dir_name: str) -> ConversationInfo | None:
    size = path.stat().st_size
    if size < 10:
        return None

    session_id = path.stem
    cwd = project_dir_name
    timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    user_count = 0

    with open(path) as f:
        for i, raw in enumerate(f):
            if i > 30:
                break
            try:
                line = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if line.get("role") == "user":
                user_count += 1

    return ConversationInfo(
        agent="cursor",
        session_id=session_id,
        path=path,
        cwd=cwd,
        timestamp=timestamp,
        size_bytes=size,
        user_messages=user_count,
    )


# ---------------------------------------------------------------------------
# Codex: ~/.codex/sessions/<year>/<month>/<day>/<name>.jsonl
# First line is {type: "session_meta", payload: {id, cwd, timestamp, ...}}
# ---------------------------------------------------------------------------


def _discover_codex() -> list[ConversationInfo]:
    if not CODEX_SESSIONS_DIR.is_dir():
        return []

    results = []
    for jsonl in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
        info = _parse_codex_meta(jsonl)
        if info:
            results.append(info)
    return results


def _parse_codex_meta(path: Path) -> ConversationInfo | None:
    size = path.stat().st_size
    if size < 10:
        return None

    session_id = ""
    cwd = ""
    timestamp = None

    with open(path) as f:
        raw = f.readline()
        if not raw.strip():
            return None
        try:
            line = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        if line.get("type") == "session_meta":
            payload = line.get("payload", {})
            session_id = payload.get("id", "")
            cwd = payload.get("cwd", "")
            ts_str = payload.get("timestamp") or line.get("timestamp")
            if ts_str:
                timestamp = _parse_iso(ts_str)

    if not session_id:
        session_id = path.stem

    if not timestamp:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    return ConversationInfo(
        agent="codex",
        session_id=session_id,
        path=path,
        cwd=cwd,
        timestamp=timestamp,
        size_bytes=size,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_AGENT_DISCOVERERS = {
    "claude": _discover_claude,
    "cursor": _discover_cursor,
    "codex": _discover_codex,
}


def _encode_cursor_dir(path: str) -> str:
    return path.lstrip("/").replace("/", "-").replace(".", "-").replace("_", "-")


def _cwd_matches(cwd: str, prefix: str, cursor_prefix: str) -> bool:
    if not cwd:
        return False
    if cwd.startswith("/"):
        return cwd.startswith(prefix)
    return cwd.startswith(cursor_prefix)


def discover_conversations(
    agents: list[str] | None = None,
    repo_dir: str | Path | None = None,
) -> list[ConversationInfo]:
    """Find historical conversations, optionally scoped to a repo directory."""
    targets = agents or list(_AGENT_DISCOVERERS.keys())
    results: list[ConversationInfo] = []
    for agent in targets:
        fn = _AGENT_DISCOVERERS.get(agent)
        if fn:
            results.extend(fn())

    if repo_dir is not None:
        prefix = str(Path(repo_dir).resolve())
        cursor_prefix = _encode_cursor_dir(prefix)
        results = [c for c in results if _cwd_matches(c.cwd, prefix, cursor_prefix)]

    results.sort(key=lambda c: c.timestamp, reverse=True)
    return results


def summarize_discovery(conversations: list[ConversationInfo]) -> dict[str, dict]:
    """Return {agent: {count, total_size_bytes}} for display."""
    summary: dict[str, dict] = {}
    for c in conversations:
        if c.agent not in summary:
            summary[c.agent] = {"count": 0, "total_size_bytes": 0}
        summary[c.agent]["count"] += 1
        summary[c.agent]["total_size_bytes"] += c.size_bytes
    return summary


def upload_conversation(client, workspace_id: str, conv: ConversationInfo) -> dict:
    """Upload a single conversation transcript + push a summary event."""
    result = client.upload_transcript(
        workspace_id=workspace_id,
        session_id=conv.session_id,
        transcript_path=conv.path,
        agent_name=conv.agent,
        cwd=conv.cwd,
    )

    client.push_event(
        workspace_id=workspace_id,
        agent_name=conv.agent,
        event_type="session_end",
        content=f"Imported historical session ({_fmt_size(conv.size_bytes)})",
        session_id=conv.session_id,
        metadata={
            "cwd": conv.cwd,
            "imported": True,
            "source": "history_import",
        },
        created_at=conv.timestamp.isoformat(),
    )
    return result


def _parse_iso(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n // 1024} KB"
    return f"{n // 1024 // 1024} MB"
