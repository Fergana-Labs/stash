"""Sessions router: GUI-friendly endpoints for browsing and sharing sessions.

A "session" in Stash is a sequence of `history_events` rows tied by
session_id. The CLI's `stash share` materializes a session into a page
from a local .jsonl file. This router provides the same materialize step
server-side, sourced from the events the scope already has, so the
session viewer can ship a Share button without involving the CLI.
"""

import json
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..auth import get_current_user, get_scope
from ..config import settings
from ..database import get_pool
from ..services import (
    linear_ticket_service,
    memory_service,
    permission_service,
    security_audit_service,
    session_folder_service,
    session_ref_service,
    session_service,
    session_title_service,
    storage_service,
)

router = APIRouter(prefix="/api/v1", tags=["sessions"])


# Stable name for the auto-created folder that holds materialized sessions.
class SessionUpsertRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    agent_name: str = Field("", max_length=64)
    cwd: str | None = Field(None, max_length=1024)
    files_touched: list[str] = Field(default_factory=list)
    # LEGACY filing lane for installed clients (Heavi's backend foremost):
    # honored when sent, read by nothing new, no default resolved.
    session_folder_id: UUID | None = None


def _session_app_url(session_id: str) -> str:
    # Session ids are the developer's own strings — slashes included — so the
    # deep link encodes the whole id into one path segment.
    return f"{settings.PUBLIC_URL.rstrip('/')}/sessions/{quote(session_id, safe='')}"


def _session_response(row: dict, title: str | None = None) -> dict:
    files_touched = row.get("files_touched") or []
    if isinstance(files_touched, str):
        files_touched = json.loads(files_touched)
    return {
        "id": str(row["id"]),
        "owner_user_id": str(row["owner_user_id"]),
        "session_id": row["session_id"],
        "app_url": _session_app_url(row["session_id"]),
        "title": title
        or session_title_service.title_from_text(
            row.get("title_source"),
            row["session_id"],
        ),
        "linear_tickets": linear_ticket_service.tickets_response(row.get("linear_tickets")),
        "agent_name": row.get("agent_name") or "",
        "cwd": row.get("cwd"),
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
    owner_user_id: UUID | None = Query(None),
    session_id_prefix: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Recent sessions across the user's accessible scopes, grouped by
    session_id. Each row carries the agent name, event count, first & last
    timestamps, and a preview of the first prompt.

    `session_id_prefix` narrows to one family of sessions by id — the chat
    sidebar asks for `agent-` so a user whose recent window is full of recorded
    CLI transcripts still sees their web chats; filtering client-side loses
    every chat that falls outside the window.
    `offset` pages through the (last_event_at DESC) order for infinite scroll."""
    # The personal view spans every accessible scope (own + shared + workspace);
    # switching into a workspace narrows the window to that scope's sessions.
    if owner_user_id is None and scope_user_id != current_user["id"]:
        owner_user_id = scope_user_id
    pool = get_pool()
    args: list = [current_user["id"]]
    # Sessions rows are the unit here, not events: pick the page of sessions
    # first (ordered by the last_event_at column ingest maintains), then read
    # only that page's events for counts and title previews. The old shape
    # aggregated every accessible history_events row before applying the
    # limit, so an empty page still paid for the user's whole event history.
    accessible_ws = permission_service.accessible_scope_ids_sql(1)
    where = [
        "s.deleted_at IS NULL",
        # An empty session shell (row created, no events yet) stays hidden
        # until its first event lands — same behavior the event-driven query
        # had for free. One index probe per candidate row.
        "EXISTS (SELECT 1 FROM history_events shell_he "
        "        WHERE shell_he.owner_user_id = s.owner_user_id "
        "          AND shell_he.session_id = s.session_id)",
        f"s.owner_user_id IN {accessible_ws}",
        permission_service.readable_content_condition("session", "s", 1),
    ]
    if owner_user_id is not None:
        args.append(owner_user_id)
        where.append(f"s.owner_user_id = ${len(args)}")
    if session_id_prefix is not None:
        args.append(session_id_prefix)
        # starts_with, not LIKE: the prefix is caller-supplied and LIKE would
        # read '%' and '_' in it as wildcards.
        where.append(f"starts_with(s.session_id, ${len(args)})")

    rows = await pool.fetch(
        f"""
        WITH page AS (
          SELECT s.id, s.owner_user_id, s.session_id, s.agent_name, s.created_by,
                 s.session_folder_id, s.started_at, s.last_event_at
          FROM sessions s
          WHERE {" AND ".join(where)}
          ORDER BY s.last_event_at DESC, s.session_id ASC, s.owner_user_id ASC
          LIMIT {int(limit)} OFFSET {int(offset)}
        )
        SELECT
          p.session_id,
          p.id AS id,
          p.owner_user_id,
          owner.display_name AS owner_name,
          {linear_ticket_service.sql_json_agg("p")} AS linear_tickets,
          NULLIF(author.display_name, '') AS user_name,
          p.agent_name,
          sf.name AS session_folder_name,
          title.title_source,
          counts.event_count,
          p.started_at,
          p.last_event_at
        FROM page p
        LEFT JOIN users owner ON owner.id = p.owner_user_id
        LEFT JOIN users author ON author.id = p.created_by
        LEFT JOIN session_folders sf ON sf.id = p.session_folder_id
        LEFT JOIN LATERAL (
          SELECT COUNT(*)::INT AS event_count
          FROM history_events he
          WHERE he.owner_user_id = p.owner_user_id AND he.session_id = p.session_id
        ) counts ON TRUE
        LEFT JOIN LATERAL (
          SELECT LEFT(he.content, 240) AS title_source
          FROM history_events he
          WHERE he.owner_user_id = p.owner_user_id AND he.session_id = p.session_id
            AND NULLIF(BTRIM(he.content), '') IS NOT NULL
          ORDER BY
            CASE
              WHEN he.event_type IN ('user_message', 'user_prompt', 'prompt', 'message', 'user') THEN 0
              WHEN he.event_type IN ('assistant_message', 'assistant') THEN 1
              ELSE 2
            END,
            he.created_at,
            he.id
          LIMIT 1
        ) title ON TRUE
        ORDER BY p.last_event_at DESC, user_name ASC, p.session_id ASC
        """,
        *args,
    )
    sessions = [dict(r) for r in rows]
    for session in sessions:
        if not session["user_name"]:
            raise RuntimeError(f"Session {session['session_id']} has no author display_name")
    sessions_by_scope: dict[UUID, list[dict]] = {}
    for session in sessions:
        sessions_by_scope.setdefault(session["owner_user_id"], []).append(session)
    for session_group in sessions_by_scope.values():
        titles = await session_title_service.titles_for_sessions(
            session_group[0]["owner_user_id"],
            session_group,
        )
        for session in session_group:
            session["title"] = titles[session["session_id"]]
            session.pop("title_source", None)
            session["linear_tickets"] = linear_ticket_service.tickets_response(
                session.get("linear_tickets")
            )
    return {"sessions": sessions}


@router.post("/me/sessions", status_code=201)
async def upsert_session(
    req: SessionUpsertRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    # Sessions land in the active scope: personal by default, or a workspace
    # when the plugin/CLI sends X-Stash-Scope (get_scope already 403s
    # non-members, so no separate write check is needed).
    owner_user_id = scope_user_id

    if (
        req.session_folder_id is not None
        and not await session_folder_service.can_add_session_to_folder(
            owner_user_id=owner_user_id,
            user_id=current_user["id"],
            folder_id=req.session_folder_id,
        )
    ):
        raise HTTPException(status_code=404, detail="Session folder not found")

    row = await session_service.upsert_session(
        owner_user_id=owner_user_id,
        session_id=req.session_id,
        agent_name=req.agent_name,
        cwd=req.cwd,
        created_by=current_user["id"],
        session_folder_id=req.session_folder_id,
    )
    if req.files_touched:
        await session_service.set_files_touched(row["id"], req.files_touched)
        row = await session_service.get_session_by_id(row["id"])
    return _session_response(row)


async def _session_detail_payload(
    owner_user_id: UUID, session_id: str, user_id: UUID
) -> dict | None:
    """Full session detail if the user may read it, else None.

    No ownership pre-gate: a session may be shared with a
    user who does not own the scope. can_read_session enforces check_access (owner OR share OR
    open skill).
    """
    if not await memory_service.can_read_session(owner_user_id, session_id, user_id):
        return None

    session = await session_service.get_session(owner_user_id, session_id)
    if not session:
        return None

    events = await memory_service.read_session_events(owner_user_id, session_id, user_id)
    payload = _session_response(
        session,
        title=await session_title_service.title_for_events(owner_user_id, session_id, events),
    )
    payload["linear_tickets"] = await linear_ticket_service.list_session_labels(session["id"])
    payload["artifacts"] = await _session_artifacts(session["id"])
    return payload


@router.get("/me/sessions/resolve")
async def resolve_my_session(
    ref: str = Query(..., min_length=1, max_length=256),
    trashed: bool = Query(
        False, description="Resolve against the trash instead (`stash restore`)."
    ),
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """What session a handle names — a title, the VFS's spelling of one, a
    `/sessions/<name>` directory name, a session_id, or a row id.

    `matched` is false for a handle that names no title: `session_id` and `id`
    then echo the handle, since it is already an id and the endpoint that uses
    it will reject it if it is not. Callers need no branch either way.

    Declared above `/me/sessions/{session_id}` so the literal path wins.
    """
    try:
        if trashed:
            return await session_ref_service.resolve_trashed(scope_user_id, ref)
        return await session_ref_service.resolve(scope_user_id, current_user["id"], ref)
    except session_ref_service.SessionRefAmbiguous as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


# session_id rides in the query, never the path: it is the developer's own
# string and may contain anything, slashes included.
@router.get("/sessions/detail")
async def get_session_canonical(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """session_id is unique per scope, not globally; when the same
    session exists in several scopes, return the newest one the caller
    can read. Any failure is a 404: an unscoped lookup must not confirm
    that an unreadable session exists."""
    for row in await session_service.list_sessions_for_session_id(session_id):
        payload = await _session_detail_payload(
            row["owner_user_id"], session_id, current_user["id"]
        )
        if payload:
            return payload
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/me/sessions/detail")
async def get_my_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    owner_user_id = scope_user_id
    payload = await _session_detail_payload(owner_user_id, session_id, current_user["id"])
    if not payload:
        raise HTTPException(status_code=404, detail="Session not found")
    return payload


class SessionTitleRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


@router.patch("/me/sessions/title")
async def rename_my_session(
    session_id: str,
    body: SessionTitleRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    owner_user_id = scope_user_id
    if not await memory_service.can_read_session(owner_user_id, session_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Session not found")

    session = await session_service.get_session(owner_user_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    can_write = await permission_service.check_access(
        "session",
        session["id"],
        current_user["id"],
        owner_user_id=owner_user_id,
        require="write",
    )
    if not can_write:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        title = await session_title_service.set_user_title(owner_user_id, session_id, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"title": title}


async def _check_session_write(
    owner_user_id: UUID,
    session_row_id: UUID,
    user_id: UUID,
) -> dict:
    """Resolve a session row that the user is allowed to mutate.

    Returns the raw row (including trashed). The trash flows need to
    operate on rows the live-only `get_session_by_id` won't return.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, owner_user_id FROM sessions WHERE id = $1",
        session_row_id,
    )
    if not row or row["owner_user_id"] != owner_user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    can_write = await permission_service.check_access(
        "session",
        session_row_id,
        user_id,
        owner_user_id=owner_user_id,
        require="write",
    )
    if not can_write:
        raise HTTPException(status_code=404, detail="Session not found")
    return dict(row)


@router.delete("/me/sessions/{session_row_id}", status_code=204)
async def delete_my_session(
    session_row_id: UUID,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    owner_user_id = scope_user_id
    """Soft delete: stamps deleted_at + deleted_by."""
    await _check_session_write(owner_user_id, session_row_id, current_user["id"])
    deleted = await session_service.delete_session(
        session_row_id, owner_user_id, current_user["id"]
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/me/sessions/{session_row_id}/restore", status_code=204)
async def restore_my_session(
    session_row_id: UUID,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    owner_user_id = scope_user_id
    await _check_session_write(owner_user_id, session_row_id, current_user["id"])
    restored = await session_service.restore_session(
        session_row_id, owner_user_id, current_user["id"]
    )
    if not restored:
        raise HTTPException(status_code=404, detail="Session not in trash")


@router.delete("/me/sessions/{session_row_id}/purge", status_code=204)
async def purge_my_session(
    session_row_id: UUID,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    owner_user_id = scope_user_id
    """Permanent delete — only callable on a session already in trash."""
    await _check_session_write(owner_user_id, session_row_id, current_user["id"])
    storage_keys = await session_service.list_trashed_session_artifact_storage_keys(
        session_row_id,
        owner_user_id,
    )
    for storage_key in storage_keys:
        await storage_service.delete_file(storage_key)
    purged = await session_service.purge_session(session_row_id, owner_user_id)
    if not purged:
        raise HTTPException(status_code=404, detail="Session not in trash")
    await security_audit_service.record_content_lifecycle_event(
        operation="purged",
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        target_type="session",
        target_id=session_row_id,
        metadata={"storage_key_count": len(storage_keys)},
    )


@router.post("/me/sessions/{session_row_id}/artifacts", status_code=201)
async def upload_session_artifact(
    session_row_id: UUID,
    file: UploadFile = File(...),
    file_path: str = Form(...),
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    owner_user_id = scope_user_id
    session = await session_service.get_session_by_id(session_row_id)
    if not session or session["owner_user_id"] != owner_user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    can_write = await permission_service.check_access(
        "session",
        session_row_id,
        current_user["id"],
        owner_user_id=owner_user_id,
        require="write",
    )
    if not can_write:
        raise HTTPException(status_code=404, detail="Session not found")
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    content = await file.read()
    max_artifact_size = 1 * 1024 * 1024
    if len(content) > max_artifact_size:
        raise HTTPException(status_code=413, detail="Artifact too large (max 1 MB)")

    storage_key = await storage_service.upload_file(
        str(owner_user_id),
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


# --- LEGACY path shapes -----------------------------------------------------
# Same story as the transcript aliases: installed clients read sessions by
# /{session_id} path shapes. Registered last so every static route above
# (detail, resolve, agent-names, …) wins. Dies with the legacy cutover.


@router.get("/sessions/{session_id}")
async def get_session_canonical_legacy(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await get_session_canonical(session_id, current_user)


@router.get("/me/sessions/{session_id}")
async def get_my_session_legacy(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    return await get_my_session(session_id, current_user, scope_user_id)


@router.patch("/me/sessions/{session_id}/title")
async def rename_my_session_legacy(
    session_id: str,
    body: SessionTitleRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    return await rename_my_session(session_id, body, current_user, scope_user_id)
