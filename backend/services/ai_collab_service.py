"""Service layer for ai-collab session history."""

from __future__ import annotations

from typing import Any

from ..database import get_pool


async def upsert_session(
    session_id: str,
    user_id: str,
    user_name: str,
    repo_url: str,
    branch: str | None = None,
    head_sha: str | None = None,
    cwd: str | None = None,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO ai_collab_sessions (id, repo_url, user_name, agent_type, branch, head_sha_start, cwd)
        VALUES ($1, $2, $3, 'claude-code', $4, $5, $6)
        ON CONFLICT (id) DO UPDATE SET
            head_sha_end = EXCLUDED.head_sha_start,
            ended_at = now()
        RETURNING *
        """,
        session_id, repo_url, user_name, branch, head_sha, cwd,
    )
    return dict(row)


async def end_session(session_id: str, head_sha: str | None = None) -> None:
    pool = get_pool()
    await pool.execute(
        """
        UPDATE ai_collab_sessions
        SET ended_at = now(), head_sha_end = coalesce($1, head_sha_end)
        WHERE id = $2
        """,
        head_sha, session_id,
    )


async def insert_event(
    session_id: str,
    event_type: str,
    head_sha: str,
    data: dict[str, Any],
    summary: str | None = None,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO ai_collab_events (session_id, event_type, head_sha, data, summary)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        RETURNING id, session_id, event_type, timestamp
        """,
        session_id, event_type, head_sha,
        __import__("json").dumps(data), summary,
    )
    return dict(row)


async def insert_commit(
    sha: str,
    session_id: str,
    repo_url: str,
    message: str | None = None,
    author: str | None = None,
) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO ai_collab_commits (sha, session_id, repo_url, message, author)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (sha) DO NOTHING
        """,
        sha, session_id, repo_url, message, author,
    )


async def recent_sessions(
    repo_url: str,
    limit: int = 10,
    since_hours: int | None = None,
    branch: str | None = None,
) -> list[dict]:
    pool = get_pool()
    clauses = ["repo_url = $1"]
    params: list[Any] = [repo_url]
    idx = 2

    if since_hours:
        clauses.append(f"started_at >= now() - interval '{since_hours} hours'")
    if branch:
        clauses.append(f"branch = ${idx}")
        params.append(branch)
        idx += 1

    params.append(limit)
    where = " AND ".join(clauses)

    rows = await pool.fetch(
        f"""
        SELECT id, user_name, agent_type, branch, head_sha_start, head_sha_end,
               started_at, ended_at
        FROM ai_collab_sessions
        WHERE {where}
        ORDER BY started_at DESC
        LIMIT ${idx}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def session_events(session_id: str) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, event_type, head_sha, timestamp, summary, data
        FROM ai_collab_events
        WHERE session_id = $1
        ORDER BY timestamp ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]


async def session_by_id(session_id: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM ai_collab_sessions WHERE id = $1",
        session_id,
    )
    return dict(row) if row else None


async def commit_by_sha(sha: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT c.*, s.user_name, s.branch, s.started_at as session_started,
               s.ended_at as session_ended
        FROM ai_collab_commits c
        LEFT JOIN ai_collab_sessions s ON c.session_id = s.id
        WHERE c.sha = $1
        """,
        sha,
    )
    return dict(row) if row else None


async def search_events(
    repo_url: str,
    query: str,
    limit: int = 20,
) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT e.id, e.session_id, e.event_type, e.head_sha, e.timestamp,
               e.summary, s.user_name, s.branch
        FROM ai_collab_events e
        JOIN ai_collab_sessions s ON e.session_id = s.id
        WHERE s.repo_url = $1
          AND to_tsvector('english', coalesce(e.summary, '')) @@ plainto_tsquery('english', $2)
        ORDER BY e.timestamp DESC
        LIMIT $3
        """,
        repo_url, query, limit,
    )
    return [dict(r) for r in rows]
