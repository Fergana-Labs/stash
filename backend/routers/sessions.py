"""Sessions router: GUI-friendly endpoints for browsing and sharing sessions.

A "session" in Stash is a sequence of `history_events` rows tied by
session_id. The CLI's `stash share` materializes a session into a notebook
page from a local .jsonl file. This router provides the same materialize
step server-side, sourced from the events the workspace already has, so the
frontend /history page can ship a Share button without involving the CLI.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..database import get_pool
from ..services import notebook_service, workspace_service

router = APIRouter(prefix="/api/v1", tags=["sessions"])

# Stable name for the auto-created notebook that holds materialized sessions.
SESSIONS_NOTEBOOK_NAME = "Sessions"


@router.get("/me/sessions")
async def list_my_sessions(
    workspace_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Recent sessions across the user's accessible workspaces, grouped by
    session_id. Each row carries the agent name, event count, first & last
    timestamps, and a preview of the first prompt."""
    pool = get_pool()
    args: list = [current_user["id"]]
    where = [
        "he.session_id IS NOT NULL",
        "(he.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1) "
        "OR he.created_by = $1)",
    ]
    if workspace_id is not None:
        args.append(workspace_id)
        where.append(f"he.workspace_id = ${len(args)}")

    rows = await pool.fetch(
        f"""
        SELECT
          he.session_id,
          he.workspace_id,
          w.name AS workspace_name,
          MAX(he.agent_name) AS agent_name,
          COUNT(*)::INT AS event_count,
          MIN(he.created_at) AS started_at,
          MAX(he.created_at) AS last_event_at,
          (
            SELECT LEFT(content, 240) FROM history_events
            WHERE session_id = he.session_id AND event_type IN ('user_prompt', 'prompt', 'message')
            ORDER BY created_at LIMIT 1
          ) AS first_prompt_preview
        FROM history_events he
        LEFT JOIN workspaces w ON w.id = he.workspace_id
        WHERE {' AND '.join(where)}
        GROUP BY he.session_id, he.workspace_id, w.name
        ORDER BY last_event_at DESC
        LIMIT {int(limit)}
        """,
        *args,
    )
    return {"sessions": [dict(r) for r in rows]}


async def _find_or_create_sessions_notebook(workspace_id: UUID, user_id: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, name, description, created_by, created_at, updated_at "
        "FROM notebooks WHERE workspace_id = $1 AND name = $2 LIMIT 1",
        workspace_id,
        SESSIONS_NOTEBOOK_NAME,
    )
    if row:
        return dict(row)
    return await notebook_service.create_notebook(
        workspace_id=workspace_id,
        name=SESSIONS_NOTEBOOK_NAME,
        description="Materialized agent sessions, auto-created when you share a session.",
        created_by=user_id,
    )


def _format_session_markdown(events: list[dict]) -> str:
    if not events:
        return "_No events in this session._"
    parts: list[str] = []
    started_at = events[0]["created_at"]
    parts.append(f"_Started {started_at.isoformat()} · {len(events)} events_\n")
    for ev in events:
        agent = ev["agent_name"] or "agent"
        etype = ev["event_type"] or "event"
        tool = ev["tool_name"]
        header = f"### {agent} · {etype}"
        if tool:
            header += f" · `{tool}`"
        parts.append(header)
        content = (ev["content"] or "").strip()
        if content:
            parts.append(content)
        parts.append("")
    return "\n".join(parts)


@router.post("/workspaces/{workspace_id}/sessions/{session_id}/materialize")
async def materialize_session(
    workspace_id: UUID,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Idempotent: turn a session_id into a notebook page in the workspace's
    Sessions notebook, returning the page so the frontend can open ShareSheet
    on it. Re-materializing the same session updates the existing page rather
    than spawning duplicates."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    pool = get_pool()
    events = await pool.fetch(
        "SELECT agent_name, event_type, tool_name, content, created_at "
        "FROM history_events WHERE session_id = $1 AND workspace_id = $2 "
        "ORDER BY created_at",
        session_id,
        workspace_id,
    )
    if not events:
        raise HTTPException(status_code=404, detail="No events for that session in this workspace")

    notebook = await _find_or_create_sessions_notebook(workspace_id, current_user["id"])

    # Title format: "{agent} · {date} · {short_id}". Naive prefix-truncation
    # produced ugly names like "Session session-" for non-UUID session_ids;
    # combining agent + date + short_id reads naturally and avoids collisions
    # within an agent in the same minute.
    agent = (events[0]["agent_name"] or "agent").strip() or "agent"
    started = events[0]["created_at"]
    date_str = started.strftime("%Y-%m-%d %H:%M")
    short_id = session_id.removeprefix("session-").removeprefix("session_")[:6] or session_id[:6]
    page_name = f"{agent} · {date_str} · {short_id}"
    content = _format_session_markdown([dict(e) for e in events])

    # Idempotency by metadata.session_id, not by name — that way we can change
    # the display name format without orphaning previously-materialized pages.
    existing = await pool.fetchrow(
        "SELECT id FROM notebook_pages "
        "WHERE notebook_id = $1 AND metadata->>'session_id' = $2 LIMIT 1",
        notebook["id"],
        session_id,
    )
    if existing:
        page = await notebook_service.update_page(
            existing["id"],
            notebook["id"],
            current_user["id"],
            content=content,
        )
    else:
        page = await notebook_service.create_page(
            notebook_id=notebook["id"],
            name=page_name,
            content=content,
            created_by=current_user["id"],
            metadata={"session_id": session_id, "materialized": True},
        )
    return {"page": page, "notebook_id": str(notebook["id"])}
