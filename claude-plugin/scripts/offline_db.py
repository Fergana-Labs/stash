"""Local SQLite database for offline mode.

Mirrors the cloud PostgreSQL schema (history_events, notebook_pages) with FTS5
for text search. Events queue locally when offline and sync to cloud on reconnect.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS history_events (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    session_id TEXT,
    tool_name TEXT,
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    synced INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notebook_pages (
    id TEXT PRIMARY KEY,
    notebook_id TEXT NOT NULL,
    name TEXT NOT NULL,
    content_markdown TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    updated_at TEXT NOT NULL,
    synced INTEGER DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS history_events_fts USING fts5(
    content, content=history_events, content_rowid=rowid
);

CREATE VIRTUAL TABLE IF NOT EXISTS notebook_pages_fts USING fts5(
    content_markdown, content=notebook_pages, content_rowid=rowid
);

-- FTS sync triggers
CREATE TRIGGER IF NOT EXISTS history_events_ai AFTER INSERT ON history_events BEGIN
    INSERT INTO history_events_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS history_events_ad AFTER DELETE ON history_events BEGIN
    INSERT INTO history_events_fts(history_events_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS history_events_au AFTER UPDATE ON history_events BEGIN
    INSERT INTO history_events_fts(history_events_fts, rowid, content) VALUES('delete', old.rowid, old.content);
    INSERT INTO history_events_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS notebook_pages_ai AFTER INSERT ON notebook_pages BEGIN
    INSERT INTO notebook_pages_fts(rowid, content_markdown) VALUES (new.rowid, new.content_markdown);
END;
CREATE TRIGGER IF NOT EXISTS notebook_pages_ad AFTER DELETE ON notebook_pages BEGIN
    INSERT INTO notebook_pages_fts(notebook_pages_fts, rowid, content_markdown) VALUES('delete', old.rowid, old.content_markdown);
END;
CREATE TRIGGER IF NOT EXISTS notebook_pages_au AFTER UPDATE ON notebook_pages BEGIN
    INSERT INTO notebook_pages_fts(notebook_pages_fts, rowid, content_markdown) VALUES('delete', old.rowid, old.content_markdown);
    INSERT INTO notebook_pages_fts(rowid, content_markdown) VALUES (new.rowid, new.content_markdown);
END;

CREATE INDEX IF NOT EXISTS idx_events_synced ON history_events(synced) WHERE synced = 0;
CREATE INDEX IF NOT EXISTS idx_events_created ON history_events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON history_events(event_type);
CREATE INDEX IF NOT EXISTS idx_pages_synced ON notebook_pages(synced) WHERE synced = 0;
"""


def _get_conn(db_path: Path) -> sqlite3.Connection:
    global _conn
    if _conn is None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(db_path))
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
    return _conn


def init_db(db_path: Path) -> None:
    """Ensure the database and tables exist."""
    _get_conn(db_path)


def close() -> None:
    """Close the database connection."""
    global _conn
    if _conn:
        _conn.close()
        _conn = None


# --- Event operations ---


def queue_event(
    db_path: Path,
    store_id: str,
    agent_name: str,
    event_type: str,
    content: str,
    session_id: str | None = None,
    tool_name: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Queue an event locally (synced=0). Returns event ID."""
    conn = _get_conn(db_path)
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO history_events (id, store_id, agent_name, event_type, content, "
        "session_id, tool_name, metadata, created_at, synced) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (event_id, store_id, agent_name, event_type, content,
         session_id, tool_name, json.dumps(metadata or {}), now),
    )
    conn.commit()
    return event_id


def get_pending_events(db_path: Path, limit: int = 100) -> list[dict]:
    """Get events that haven't been synced to cloud."""
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM history_events WHERE synced = 0 ORDER BY created_at LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_events(db_path: Path, limit: int = 20, event_type: str | None = None) -> list[dict]:
    """Get recent events for injection scoring."""
    conn = _get_conn(db_path)
    if event_type:
        rows = conn.execute(
            "SELECT * FROM history_events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
            (event_type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM history_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def search_events_fts(db_path: Path, query: str, limit: int = 30) -> list[dict]:
    """FTS5 search on history events."""
    conn = _get_conn(db_path)
    # Escape special FTS5 characters
    safe_query = query.replace('"', '""')
    try:
        rows = conn.execute(
            "SELECT e.*, rank FROM history_events e "
            "JOIN history_events_fts f ON e.rowid = f.rowid "
            "WHERE history_events_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (f'"{safe_query}"', limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # FTS query syntax error — fall back to LIKE
        rows = conn.execute(
            "SELECT *, 0.5 as rank FROM history_events WHERE content LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_event(db_path: Path, event: dict) -> None:
    """Insert or update an event from cloud (last-write-wins on created_at)."""
    conn = _get_conn(db_path)
    conn.execute(
        "INSERT INTO history_events (id, store_id, agent_name, event_type, content, "
        "session_id, tool_name, metadata, created_at, synced) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1) "
        "ON CONFLICT(id) DO UPDATE SET "
        "content = excluded.content, metadata = excluded.metadata, synced = 1 "
        "WHERE excluded.created_at > history_events.created_at",
        (str(event["id"]), str(event.get("store_id", "")), event.get("agent_name", ""),
         event.get("event_type", ""), event.get("content", ""),
         event.get("session_id"), event.get("tool_name"),
         json.dumps(event.get("metadata", {})),
         str(event.get("created_at", ""))),
    )
    conn.commit()


def mark_events_synced(db_path: Path, event_ids: list[str]) -> None:
    """Mark events as synced after successful cloud upload."""
    if not event_ids:
        return
    conn = _get_conn(db_path)
    placeholders = ",".join("?" * len(event_ids))
    conn.execute(f"UPDATE history_events SET synced = 1 WHERE id IN ({placeholders})", event_ids)
    conn.commit()


# --- Notebook page operations ---


def get_pending_pages(db_path: Path, limit: int = 100) -> list[dict]:
    """Get pages that haven't been synced."""
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM notebook_pages WHERE synced = 0 ORDER BY updated_at LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def search_pages_fts(db_path: Path, query: str, limit: int = 10) -> list[dict]:
    """FTS5 search on notebook pages."""
    conn = _get_conn(db_path)
    safe_query = query.replace('"', '""')
    try:
        rows = conn.execute(
            "SELECT p.*, rank FROM notebook_pages p "
            "JOIN notebook_pages_fts f ON p.rowid = f.rowid "
            "WHERE notebook_pages_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (f'"{safe_query}"', limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT *, 0.5 as rank FROM notebook_pages WHERE content_markdown LIKE ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_page(db_path: Path, page: dict) -> None:
    """Insert or update a page from cloud (last-write-wins on updated_at)."""
    conn = _get_conn(db_path)
    conn.execute(
        "INSERT INTO notebook_pages (id, notebook_id, name, content_markdown, metadata, updated_at, synced) "
        "VALUES (?, ?, ?, ?, ?, ?, 1) "
        "ON CONFLICT(id) DO UPDATE SET "
        "name = excluded.name, content_markdown = excluded.content_markdown, "
        "metadata = excluded.metadata, updated_at = excluded.updated_at, synced = 1 "
        "WHERE excluded.updated_at > notebook_pages.updated_at",
        (str(page["id"]), str(page.get("notebook_id", "")), page.get("name", ""),
         page.get("content_markdown", ""), json.dumps(page.get("metadata", {})),
         str(page.get("updated_at", ""))),
    )
    conn.commit()


def mark_pages_synced(db_path: Path, page_ids: list[str]) -> None:
    if not page_ids:
        return
    conn = _get_conn(db_path)
    placeholders = ",".join("?" * len(page_ids))
    conn.execute(f"UPDATE notebook_pages SET synced = 1 WHERE id IN ({placeholders})", page_ids)
    conn.commit()


# --- Sync engine ---


def sync_to_cloud(db_path: Path, client, cfg: dict) -> dict:
    """Upload pending local events and pages to cloud. Returns sync stats."""
    stats = {"events_uploaded": 0, "pages_uploaded": 0, "errors": 0}

    ws_id = cfg.get("workspace_id", "")
    store_id = cfg.get("history_store_id", "")

    # Upload pending events
    if ws_id and store_id:
        pending = get_pending_events(db_path, limit=100)
        synced_ids = []
        for evt in pending:
            try:
                client.push_event(
                    workspace_id=ws_id,
                    store_id=store_id,
                    agent_name=evt["agent_name"],
                    event_type=evt["event_type"],
                    content=evt["content"],
                    session_id=evt.get("session_id"),
                    tool_name=evt.get("tool_name"),
                    metadata=json.loads(evt.get("metadata", "{}")),
                )
                synced_ids.append(evt["id"])
                stats["events_uploaded"] += 1
            except Exception:
                stats["errors"] += 1
                break  # Stop on first failure (probably offline)

        mark_events_synced(db_path, synced_ids)

    return stats


def sync_from_cloud(db_path: Path, client, cfg: dict) -> dict:
    """Download recent events and pages from cloud. Returns sync stats."""
    stats = {"events_downloaded": 0, "pages_downloaded": 0}

    ws_id = cfg.get("workspace_id", "")
    store_id = cfg.get("history_store_id", "")

    # Download recent events
    if ws_id and store_id:
        # Get the latest synced event timestamp
        conn = _get_conn(db_path)
        row = conn.execute(
            "SELECT MAX(created_at) as max_ts FROM history_events WHERE synced = 1"
        ).fetchone()
        after_ts = row["max_ts"] if row and row["max_ts"] else None

        try:
            events = client.query_events(
                workspace_id=ws_id, store_id=store_id,
                after=after_ts, limit=200,
            )
            for evt in events:
                upsert_event(db_path, evt)
                stats["events_downloaded"] += 1
        except Exception:
            pass  # Offline — skip download

    return stats
