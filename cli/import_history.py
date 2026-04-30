"""Discover and import historical conversations from coding agents.

Supports Claude Code, Cursor, and Codex. Each agent stores conversations as
.jsonl files in predictable locations under ~/.<agent>/. We discover them,
extract lightweight metadata (session_id, cwd, timestamp, size), and upload
them as transcript blobs + summary events.

Cursor also stores conversations in SQLite databases under
~/Library/Application Support/Cursor/User/. We read those when .jsonl files
aren't available for a workspace.
"""

from __future__ import annotations

import json
import platform
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CURSOR_PROJECTS_DIR = Path.home() / ".cursor" / "projects"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"

if platform.system() == "Darwin":
    CURSOR_STORAGE_DIR = (
        Path.home() / "Library" / "Application Support" / "Cursor" / "User"
    )
else:
    CURSOR_STORAGE_DIR = Path.home() / ".config" / "Cursor" / "User"


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
# Cursor SQLite: conversations stored in per-workspace state.vscdb + global
# state.vscdb under ~/Library/Application Support/Cursor/User/.
# ---------------------------------------------------------------------------

CURSOR_WORKSPACE_STORAGE = CURSOR_STORAGE_DIR / "workspaceStorage"
CURSOR_GLOBAL_DB = CURSOR_STORAGE_DIR / "globalStorage" / "state.vscdb"


def _discover_cursor_sqlite(repo_dir: Path | None = None) -> list[ConversationInfo]:
    """Discover Cursor conversations from SQLite for a specific repo."""
    if repo_dir is None:
        return []
    ws_dir = CURSOR_WORKSPACE_STORAGE
    if not ws_dir.is_dir() or not CURSOR_GLOBAL_DB.is_file():
        return []

    workspace_hash = _find_cursor_workspace(ws_dir, repo_dir)
    if not workspace_hash:
        return []

    ws_db_path = ws_dir / workspace_hash / "state.vscdb"
    if not ws_db_path.is_file():
        return []

    composer_ids = _extract_composer_ids(ws_db_path)
    if not composer_ids:
        return []

    cwd = str(repo_dir)
    results = []
    global_db = sqlite3.connect(f"file:{CURSOR_GLOBAL_DB}?mode=ro", uri=True)
    try:
        for composer_id in composer_ids:
            info = _parse_cursor_sqlite_conversation(global_db, composer_id, cwd)
            if info:
                results.append(info)
    finally:
        global_db.close()

    return results


def _find_cursor_workspace(ws_dir: Path, repo_dir: Path) -> str | None:
    """Find the workspace hash whose workspace.json points to repo_dir."""
    target = str(repo_dir.resolve())
    for d in ws_dir.iterdir():
        if not d.is_dir():
            continue
        ws_json = d / "workspace.json"
        if not ws_json.is_file():
            continue
        try:
            data = json.loads(ws_json.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        folder = data.get("folder", "")
        if folder.startswith("file://"):
            folder = unquote(folder[7:])
        if folder.rstrip("/") == target.rstrip("/"):
            return d.name
    return None


def _extract_composer_ids(ws_db_path: Path) -> list[str]:
    """Extract conversation (composer) UUIDs from a workspace state.vscdb."""
    ids: set[str] = set()
    db = sqlite3.connect(f"file:{ws_db_path}?mode=ro", uri=True)
    try:
        # composerChatViewPane entries contain inner aichat.view.<composer-uuid> refs
        cur = db.execute(
            "SELECT value FROM ItemTable "
            "WHERE key LIKE 'workbench.panel.composerChatViewPane.%'"
        )
        for (val,) in cur:
            try:
                data = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                continue
            for k in data:
                if "aichat.view." in k:
                    ids.add(k.split("aichat.view.")[1])

        # Also grab currently-selected composers
        cur = db.execute(
            "SELECT value FROM ItemTable WHERE key = 'composer.composerData'"
        )
        row = cur.fetchone()
        if row:
            try:
                data = json.loads(row[0])
                for uid in data.get("selectedComposerIds", []):
                    ids.add(uid)
            except (json.JSONDecodeError, TypeError):
                pass
    finally:
        db.close()
    return list(ids)


def _parse_cursor_sqlite_conversation(
    db: sqlite3.Connection, composer_id: str, cwd: str
) -> ConversationInfo | None:
    """Read a single conversation's metadata from the global Cursor DB."""
    cur = db.execute(
        "SELECT value FROM cursorDiskKV WHERE key = ?",
        (f"composerData:{composer_id}",),
    )
    row = cur.fetchone()
    if not row:
        return None

    val = row[0]
    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="replace")
    try:
        data = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return None

    created = data.get("createdAt")
    if isinstance(created, (int, float)):
        timestamp = datetime.fromtimestamp(created / 1000, tz=UTC)
    else:
        timestamp = datetime.now(tz=UTC)

    bubbles = data.get("fullConversationHeadersOnly", [])
    user_count = sum(1 for b in bubbles if b.get("type") == 1)

    # Estimate size from the raw composerData JSON — the actual transcript will be
    # smaller (just messages) but this gives a reasonable order-of-magnitude.
    estimated_size = len(val.encode("utf-8"))

    return ConversationInfo(
        agent="cursor",
        session_id=composer_id,
        path=Path("/dev/null"),
        cwd=cwd,
        timestamp=timestamp,
        size_bytes=estimated_size,
        user_messages=user_count,
        extras={
            "source": "sqlite",
            "name": data.get("name", ""),
            "bubble_count": len(bubbles),
        },
    )


def _materialize_cursor_conversation(conv: ConversationInfo) -> Path:
    """Extract a Cursor SQLite conversation to a temp .jsonl file for upload."""
    db = sqlite3.connect(f"file:{CURSOR_GLOBAL_DB}?mode=ro", uri=True)
    try:
        cur = db.execute(
            "SELECT value FROM cursorDiskKV WHERE key = ?",
            (f"composerData:{conv.session_id}",),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"composerData not found for {conv.session_id}")

        val = row[0]
        if isinstance(val, bytes):
            val = val.decode("utf-8", errors="replace")
        data = json.loads(val)
        bubbles = data.get("fullConversationHeadersOnly", [])

        lines = []
        for b in bubbles:
            bid = b.get("bubbleId")
            btype = b.get("type")
            if not bid:
                continue
            role = "user" if btype == 1 else "assistant"

            cur = db.execute(
                "SELECT value FROM cursorDiskKV WHERE key = ?",
                (f"bubbleId:{conv.session_id}:{bid}",),
            )
            brow = cur.fetchone()
            text = ""
            if brow:
                bval = brow[0]
                if isinstance(bval, bytes):
                    bval = bval.decode("utf-8", errors="replace")
                try:
                    bdata = json.loads(bval)
                    text = bdata.get("text", "")
                except (json.JSONDecodeError, TypeError):
                    pass

            if not text:
                continue

            lines.append(
                json.dumps(
                    {
                        "role": role,
                        "message": {"content": [{"type": "text", "text": text}]},
                    }
                )
            )
    finally:
        db.close()

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", prefix=f"cursor-{conv.session_id[:8]}-", delete=False
    )
    tmp.write("\n".join(lines))
    tmp.close()
    return Path(tmp.name)


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
        resolved = Path(repo_dir).resolve()
        prefix = str(resolved)
        cursor_prefix = _encode_cursor_dir(prefix)
        results = [c for c in results if _cwd_matches(c.cwd, prefix, cursor_prefix)]

        if "cursor" in targets:
            sqlite_ids = {c.session_id for c in results if c.agent == "cursor"}
            for conv in _discover_cursor_sqlite(resolved):
                if conv.session_id not in sqlite_ids:
                    results.append(conv)

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
    import os

    transcript_path = conv.path
    materialized = False

    if conv.extras.get("source") == "sqlite":
        transcript_path = _materialize_cursor_conversation(conv)
        materialized = True

    try:
        result = client.upload_transcript(
            workspace_id=workspace_id,
            session_id=conv.session_id,
            transcript_path=transcript_path,
            agent_name=conv.agent,
            cwd=conv.cwd,
        )
    finally:
        if materialized:
            os.unlink(transcript_path)

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
