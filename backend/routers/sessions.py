"""Sessions router: GUI-friendly endpoints for browsing and sharing sessions.

A "session" in Stash is a sequence of `history_events` rows tied by
session_id. The CLI's `stash share` materializes a session into a page
from a local .jsonl file. This router provides the same materialize step
server-side, sourced from the events the workspace already has, so the
session viewer can ship a Share button without involving the CLI.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..database import get_pool
from ..services import (
    files_tree_service,
    memory_service,
    permission_service,
    session_service,
    storage_service,
    workspace_service,
)

router = APIRouter(prefix="/api/v1", tags=["sessions"])

# Stable name for the auto-created folder that holds materialized sessions.
SESSIONS_FOLDER_NAME = "Sessions"


class SessionUpsertRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    agent_name: str = Field("", max_length=64)
    cwd: str | None = Field(None, max_length=1024)
    files_touched: list[str] = Field(default_factory=list)


def _session_response(row: dict) -> dict:
    files_touched = row.get("files_touched") or []
    if isinstance(files_touched, str):
        files_touched = json.loads(files_touched)
    return {
        "id": str(row["id"]),
        "workspace_id": str(row["workspace_id"]),
        "session_id": row["session_id"],
        "agent_name": row.get("agent_name") or "",
        "cwd": row.get("cwd"),
        "summary": row.get("summary"),
        "summary_status": row.get("summary_status"),
        "files_touched": files_touched,
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "created_by": str(row["created_by"]) if row.get("created_by") else None,
    }


async def _session_artifacts(session_row_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, file_path, storage_key, size_bytes, created_at "
        "FROM session_artifacts WHERE session_id = $1 ORDER BY created_at",
        session_row_id,
    )
    artifacts = []
    for row in rows:
        artifact = dict(row)
        artifact["id"] = str(artifact["id"])
        artifact["url"] = await storage_service.get_file_url(artifact.pop("storage_key"))
        artifacts.append(artifact)
    return artifacts


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
        f"(he.workspace_id IS NULL OR {memory_service.readable_session_event_condition('he', 1)})",
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
          COALESCE(
            MAX(NULLIF(u.display_name, '')),
            MAX(NULLIF(u.name, '')),
            'Unknown user'
          ) AS user_name,
          MAX(he.agent_name) AS agent_name,
          COUNT(*)::INT AS event_count,
          MIN(he.created_at) AS started_at,
          MAX(he.created_at) AS last_event_at,
          (
            SELECT LEFT(he2.content, 240) FROM history_events he2
            WHERE he2.session_id = he.session_id
              AND he2.workspace_id IS NOT DISTINCT FROM he.workspace_id
              AND (he2.workspace_id IS NOT NULL OR he2.created_by = $1)
              AND he2.event_type IN ('user_prompt', 'prompt', 'message')
            ORDER BY he2.created_at LIMIT 1
          ) AS first_prompt_preview
        FROM history_events he
        LEFT JOIN workspaces w ON w.id = he.workspace_id
        LEFT JOIN users u ON u.id = he.created_by
        WHERE {' AND '.join(where)}
        GROUP BY he.session_id, he.workspace_id, w.name
        ORDER BY last_event_at DESC, user_name ASC, session_id ASC
        LIMIT {int(limit)}
        """,
        *args,
    )
    return {"sessions": [dict(r) for r in rows]}


@router.post("/workspaces/{workspace_id}/sessions", status_code=201)
async def upsert_workspace_session(
    workspace_id: UUID,
    req: SessionUpsertRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    row = await session_service.upsert_session(
        workspace_id=workspace_id,
        session_id=req.session_id,
        agent_name=req.agent_name,
        cwd=req.cwd,
        created_by=current_user["id"],
    )
    if req.files_touched:
        await session_service.set_files_touched(row["id"], req.files_touched)
        row = await session_service.get_session_by_id(row["id"])
    return _session_response(row)


@router.get("/workspaces/{workspace_id}/sessions/{session_id}")
async def get_workspace_session(
    workspace_id: UUID,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not await memory_service.can_read_session(workspace_id, session_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")

    session = await session_service.get_session(workspace_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    payload = _session_response(session)
    payload["artifacts"] = await _session_artifacts(session["id"])
    return payload


@router.post("/workspaces/{workspace_id}/sessions/{session_row_id}/artifacts", status_code=201)
async def upload_session_artifact(
    workspace_id: UUID,
    session_row_id: UUID,
    file: UploadFile = File(...),
    file_path: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    session = await session_service.get_session_by_id(session_row_id)
    if not session or session["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Session not found")
    can_read = await permission_service.check_access(
        "session",
        session_row_id,
        current_user["id"],
        workspace_id=workspace_id,
    )
    if not can_read:
        raise HTTPException(status_code=404, detail="Session not found")
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    content = await file.read()
    max_artifact_size = 1 * 1024 * 1024
    if len(content) > max_artifact_size:
        raise HTTPException(status_code=413, detail="Artifact too large (max 1 MB)")

    storage_key = await storage_service.upload_file(
        str(workspace_id),
        file.filename or file_path.split("/")[-1],
        content,
        file.content_type or "application/octet-stream",
    )
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, file_path, size_bytes, created_at",
        session_row_id,
        file_path,
        storage_key,
        len(content),
    )
    return dict(row)


async def _find_or_create_sessions_folder(workspace_id: UUID, user_id: UUID) -> dict:
    return await files_tree_service.find_or_create_root_folder(
        workspace_id, SESSIONS_FOLDER_NAME, user_id
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
    """Idempotent: turn a session_id into a page in the workspace's
    Sessions folder, returning the page so the frontend can open ShareSheet
    on it. Re-materializing the same session updates the existing page rather
    than spawning duplicates."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not await memory_service.can_read_session(workspace_id, session_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="No events for that session in this workspace")

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

    folder = await _find_or_create_sessions_folder(workspace_id, current_user["id"])

    agent = (events[0]["agent_name"] or "agent").strip() or "agent"
    started = events[0]["created_at"]
    date_str = started.strftime("%Y-%m-%d %H:%M")
    short_id = session_id.removeprefix("session-").removeprefix("session_")[:6] or session_id[:6]
    page_name = f"{agent} · {date_str} · {short_id}"
    content = _format_session_markdown([dict(e) for e in events])

    # Idempotency by metadata.session_id, not by name — that way we can change
    # the display name format without orphaning previously-materialized pages.
    existing = await pool.fetchrow(
        "SELECT id FROM pages "
        "WHERE workspace_id = $1 AND folder_id = $2 AND metadata->>'session_id' = $3 LIMIT 1",
        workspace_id,
        folder["id"],
        session_id,
    )
    if existing:
        page = await files_tree_service.update_page(
            existing["id"],
            workspace_id,
            current_user["id"],
            content=content,
        )
    else:
        page = await files_tree_service.create_page(
            workspace_id=workspace_id,
            name=page_name,
            content=content,
            created_by=current_user["id"],
            folder_id=folder["id"],
            metadata={"session_id": session_id, "materialized": True},
        )
    return {"page": page, "folder_id": str(folder["id"])}
