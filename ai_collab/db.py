"""Database connection and queries for ai-collab (sync psycopg to Neon PostgreSQL)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import settings

SCHEMA = """\
CREATE TABLE IF NOT EXISTS ai_collab_sessions (
    id              TEXT PRIMARY KEY,
    repo_url        TEXT NOT NULL,
    user_name       TEXT NOT NULL,
    agent_type      TEXT NOT NULL DEFAULT 'claude-code',
    branch          TEXT,
    head_sha_start  TEXT,
    head_sha_end    TEXT,
    cwd             TEXT,
    started_at      TIMESTAMPTZ DEFAULT now(),
    ended_at        TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ai_collab_events (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT REFERENCES ai_collab_sessions(id),
    event_type      TEXT NOT NULL,
    head_sha        TEXT NOT NULL,
    timestamp       TIMESTAMPTZ DEFAULT now(),
    data            JSONB NOT NULL,
    summary         TEXT
);

CREATE TABLE IF NOT EXISTS ai_collab_commits (
    sha             TEXT PRIMARY KEY,
    session_id      TEXT REFERENCES ai_collab_sessions(id),
    repo_url        TEXT NOT NULL,
    message         TEXT,
    author          TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_collab_events_session ON ai_collab_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_collab_events_sha ON ai_collab_events(head_sha);
CREATE INDEX IF NOT EXISTS idx_ai_collab_events_type ON ai_collab_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ai_collab_sessions_repo ON ai_collab_sessions(repo_url);
CREATE INDEX IF NOT EXISTS idx_ai_collab_commits_session ON ai_collab_commits(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_collab_commits_repo ON ai_collab_commits(repo_url);
CREATE INDEX IF NOT EXISTS idx_ai_collab_events_summary_fts
    ON ai_collab_events USING GIN(to_tsvector('english', coalesce(summary, '')));
"""


def _connect() -> psycopg.Connection:
    url = settings.DATABASE_URL
    if not url:
        raise RuntimeError(
            "AI_COLLAB_DATABASE_URL is not set. "
            "Set it in your .env or environment to point at a Neon PostgreSQL database."
        )
    return psycopg.connect(url, row_factory=dict_row)


def setup_tables() -> None:
    """Create all tables and indexes (idempotent)."""
    with _connect() as conn:
        conn.execute(SCHEMA)
        conn.commit()


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def upsert_session(
    session_id: str,
    repo_url: str,
    user_name: str,
    branch: str | None = None,
    head_sha: str | None = None,
    cwd: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """\
            INSERT INTO ai_collab_sessions (id, repo_url, user_name, branch, head_sha_start, cwd)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                head_sha_end = EXCLUDED.head_sha_start,
                ended_at = now()
            """,
            (session_id, repo_url, user_name, branch, head_sha, cwd),
        )
        conn.commit()


def end_session(session_id: str, head_sha: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            """\
            UPDATE ai_collab_sessions
            SET ended_at = now(), head_sha_end = coalesce(%s, head_sha_end)
            WHERE id = %s
            """,
            (head_sha, session_id),
        )
        conn.commit()


def insert_event(
    session_id: str,
    event_type: str,
    head_sha: str,
    data: dict[str, Any],
    summary: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """\
            INSERT INTO ai_collab_events (session_id, event_type, head_sha, data, summary)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            """,
            (session_id, event_type, head_sha, psycopg.types.json.Json(data), summary),
        )
        conn.commit()


def insert_commit(
    sha: str,
    session_id: str,
    repo_url: str,
    message: str | None = None,
    author: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """\
            INSERT INTO ai_collab_commits (sha, session_id, repo_url, message, author)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (sha) DO NOTHING
            """,
            (sha, session_id, repo_url, message, author),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Read operations (for MCP tools)
# ---------------------------------------------------------------------------


def recent_sessions(
    repo_url: str,
    limit: int = 10,
    since_hours: int | None = None,
    branch: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["repo_url = %s"]
    params: list[Any] = [repo_url]

    if since_hours:
        clauses.append("started_at >= now() - interval '%s hours'")
        params.append(since_hours)
    if branch:
        clauses.append("branch = %s")
        params.append(branch)

    where = " AND ".join(clauses)
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(
            f"""\
            SELECT id, user_name, agent_type, branch, head_sha_start, head_sha_end,
                   started_at, ended_at
            FROM ai_collab_sessions
            WHERE {where}
            ORDER BY started_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
    return rows


def session_events(session_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """\
            SELECT id, event_type, head_sha, timestamp, summary, data
            FROM ai_collab_events
            WHERE session_id = %s
            ORDER BY timestamp ASC
            """,
            (session_id,),
        ).fetchall()
    return rows


def session_by_id(session_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM ai_collab_sessions WHERE id = %s",
            (session_id,),
        ).fetchone()
    return row


def commit_by_sha(sha: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """\
            SELECT c.*, s.user_name, s.branch, s.started_at as session_started,
                   s.ended_at as session_ended
            FROM ai_collab_commits c
            LEFT JOIN ai_collab_sessions s ON c.session_id = s.id
            WHERE c.sha = %s
            """,
            (sha,),
        ).fetchone()
    return row


def search_events(
    repo_url: str,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """\
            SELECT e.id, e.session_id, e.event_type, e.head_sha, e.timestamp,
                   e.summary, s.user_name, s.branch
            FROM ai_collab_events e
            JOIN ai_collab_sessions s ON e.session_id = s.id
            WHERE s.repo_url = %s
              AND to_tsvector('english', coalesce(e.summary, '')) @@ plainto_tsquery('english', %s)
            ORDER BY e.timestamp DESC
            LIMIT %s
            """,
            (repo_url, query, limit),
        ).fetchall()
    return rows


def session_count(repo_url: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT count(*) as cnt FROM ai_collab_sessions WHERE repo_url = %s",
            (repo_url,),
        ).fetchone()
    return row["cnt"] if row else 0
