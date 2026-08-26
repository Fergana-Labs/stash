"""Session transcripts: parse uploaded .jsonl[.gz] into history_events rows.

PR 1 of the duplication cleanup. The legacy R2 blob + session_transcripts
row are gone — a session's transcript is now reconstructed from the rows
in `history_events` that the CLI streamed live during the session.

Upload is treated as a backstop: if a session already has events streamed
in, the upload is a no-op. If it doesn't (e.g., a backfilled session, or
a CLI that lost connectivity mid-session), the upload parses the JSONL
and inserts the missing events.

Read side returns events as a JSON array. We don't reserialize to JSONL
just to have the client parse it back — the rows are the source of truth.
"""

import json
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..auth import get_current_user, get_scope
from ..config import settings
from ..database import get_pool
from ..services import (
    memory_service,
    security_audit_service,
    session_service,
    transcript_import,
    user_scope_service,
)
from ..tasks.agent_schedules import first_day_curator_tick

router = APIRouter(prefix="/api/v1/me/transcripts", tags=["transcripts"])

MAX_TRANSCRIPT_SIZE = 50 * 1024 * 1024

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL)
    return _redis


def _is_jsonl(filename: str | None) -> bool:
    if not filename:
        return False
    name = filename.lower()
    return name.endswith(".jsonl") or name.endswith(".jsonl.gz")


async def _check_write(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.can_write(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Only the owner can upload transcripts")


@router.post("", status_code=201)
async def upload_transcript(
    file: UploadFile,
    session_id: str = Form(...),
    agent_name: str = Form(...),
    cwd: str | None = Form(None),
    # LEGACY filing lane for installed clients: honored when sent.
    session_folder_id: UUID | None = Form(None),
    replace: bool = Form(False),
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Parse the uploaded JSONL into history_events rows.

    Existing sessions are left alone unless the caller explicitly asks to
    replace them.
    """
    # Transcripts land in the active scope, matching where the session's
    # events were pushed (X-Stash-Scope header, personal when absent).
    owner_user_id = scope_user_id
    await _check_write(owner_user_id, current_user["id"])
    if not _is_jsonl(file.filename):
        raise HTTPException(status_code=400, detail="Session uploads must be .JSONL files")
    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    body = await file.read()
    if len(body) > MAX_TRANSCRIPT_SIZE:
        raise HTTPException(status_code=413, detail="Transcript too large (max 50 MB)")

    pool = get_pool()
    existing = await pool.fetchval(
        "SELECT COUNT(*) FROM history_events WHERE owner_user_id = $1 AND session_id = $2",
        owner_user_id,
        session_id,
    )
    if existing:
        session_row = await session_service.get_session(owner_user_id, session_id)
        if session_row is None:
            # A session the user deleted keeps its events until purge; a
            # re-upload (e.g. history import) must not resurrect it — and it
            # isn't an error, so report a skip.
            deleted = await pool.fetchval(
                "SELECT 1 FROM sessions "
                "WHERE owner_user_id = $1 AND session_id = $2 AND deleted_at IS NOT NULL",
                owner_user_id,
                session_id,
            )
            if deleted:
                return {
                    "session_id": session_id,
                    "imported": 0,
                    "skipped": True,
                    "reason": "session was deleted",
                }
            # Events without any session row (legacy orphans): fall through —
            # the no-replace branch below recreates the row and skips.
        elif not await memory_service.can_read_session(
            owner_user_id, session_id, current_user["id"]
        ):
            raise HTTPException(status_code=404, detail="Transcript not found")
        if replace:
            await pool.execute(
                "DELETE FROM history_events WHERE owner_user_id = $1 AND session_id = $2",
                owner_user_id,
                session_id,
            )
        else:
            await session_service.upsert_session(
                owner_user_id,
                session_id,
                agent_name=agent_name,
                cwd=cwd,
                created_by=current_user["id"],
                session_folder_id=session_folder_id,
            )
            return {
                "session_id": session_id,
                "imported": 0,
                "skipped": True,
                "reason": "session already has events",
            }

    events = transcript_import.parse_jsonl_to_events(
        body, session_id=session_id, agent_name=agent_name
    )
    # The transcript's own event times are the truth about when the session
    # ran. A history import replays conversations from months ago, so stamping
    # the row with now() would file every one of them under today everywhere we
    # order by started_at.
    transcript_started_at = min(
        (e["created_at"] for e in events if e.get("created_at")), default=None
    )

    if not existing or replace:
        await session_service.upsert_session(
            owner_user_id,
            session_id,
            agent_name=agent_name,
            cwd=cwd,
            created_by=current_user["id"],
            session_folder_id=session_folder_id,
            started_at=transcript_started_at,
        )
    if cwd:
        for e in events:
            e["metadata"] = {**(e.get("metadata") or {}), "cwd": cwd}

    inserted = await memory_service.push_events_batch(owner_user_id, current_user["id"], events)
    if inserted:
        first_day_curator_tick.delay(str(owner_user_id))
    return {
        "session_id": session_id,
        "imported": len(inserted),
        "skipped": False,
    }


def _event_role(event_type: str | None) -> str | None:
    """user/assistant projection for the session viewer.

    tool_use events fold into 'assistant' so the timeline shows tool calls
    inline with assistant turns instead of dropping them silently."""
    if event_type in memory_service.USER_EVENT_TYPES:
        return "user"
    if event_type in memory_service.ASSISTANT_EVENT_TYPES:
        return "assistant"
    return None


def _events_to_viewer_shape(events: list[dict]) -> list[dict]:
    """Project history_events rows into the shape the session viewer renders.
    One dict per turn; downstream renderers don't need to know about row
    columns, just role + content + timing."""
    out: list[dict] = []
    for ev in events:
        role = _event_role(ev.get("event_type"))
        if role is None:
            continue
        out.append(
            {
                "id": str(ev["id"]),
                "role": role,
                "agent_name": ev.get("agent_name") or "",
                "content": ev.get("content") or "",
                "tool_name": ev.get("tool_name"),
                "created_at": ev["created_at"].isoformat() if ev.get("created_at") else None,
            }
        )
    return out


async def _resolve_readable_events(
    session_id: str, user_id: UUID
) -> tuple[UUID, list[dict]] | None:
    """session_id is unique per scope, not globally. Return (owner, events) for
    the newest scope holding this session that the caller can read — mirrors the
    canonical /sessions/{id} route so shared transcripts resolve to their real
    owner instead of being forced onto the caller's scope."""
    for row in await session_service.list_sessions_for_session_id(session_id):
        events = await memory_service.read_session_events(row["owner_user_id"], session_id, user_id)
        if events:
            return row["owner_user_id"], events
    return None


# session_id rides in the query, never the path: it is the developer's own
# string and may contain anything, slashes included.
@router.get("")
async def get_transcript_metadata(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Metadata-only response. The frontend follows up with /events for
    the bytes. No ownership gate: read_session_events enforces
    can_read_session, so a non-owner with a share can read it."""
    resolved = await _resolve_readable_events(session_id, current_user["id"])
    if not resolved:
        raise HTTPException(status_code=404, detail="Transcript not found")
    owner_user_id, events = resolved
    agent_name = events[0]["agent_name"] or ""
    cwd = ""
    for e in events:
        meta = e.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("cwd"):
            cwd = meta["cwd"]
            break
    size_bytes = sum(len(e.get("content") or "") for e in events)
    return {
        "session_id": session_id,
        "owner_user_id": str(owner_user_id),
        "agent_name": agent_name,
        "event_count": len(events),
        "size_bytes": size_bytes,
        "cwd": cwd or None,
        "started_at": events[0]["created_at"],
        "last_at": events[-1]["created_at"],
    }


@router.get("/events")
async def get_transcript_events(
    session_id: str,
    limit: int = Query(..., ge=1),
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """One page of chat-thread turns for a session, oldest first, sourced
    directly from history_events. offset is a turn ordinal, so a future
    in-session search can jump straight to a match's window.

    limit is required and has no server-side default. A default here is
    invisible to the caller, and the callers that read this route as a file
    (the VFS renders sessions/<name>/transcript.md from it) cannot tell a
    short session from a truncated one — which is exactly how every long
    transcript came to be served silently cut off. Requiring the count moves
    that decision to the caller, who is the only one who can disclose it:
    `total` and `has_more` come back on every response so it can.

    No ownership gate: can_read_session is enforced per scope below, so
    another user the session is shared with can read it."""
    for row in await session_service.list_sessions_for_session_id(session_id):
        owner_user_id = row["owner_user_id"]
        if not await memory_service.can_read_session(owner_user_id, session_id, current_user["id"]):
            continue
        events, total = await memory_service.read_session_events_page(
            owner_user_id, session_id, limit, offset
        )
        if total:
            await security_audit_service.record_content_read(
                target_type="transcript",
                target_id=session_id,
                actor_user_id=current_user["id"],
                owner_user_id=owner_user_id,
            )
            return {
                "events": _events_to_viewer_shape(events),
                "total": total,
                "has_more": offset + len(events) < total,
            }
    raise HTTPException(status_code=404, detail="Transcript not found")


@router.get("/export.jsonl")
async def export_transcript_jsonl(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """JSONL projection of the session — one event per line. No ownership
    gate: read_session_events enforces can_read_session, so a user with
    a share can export it."""
    import json as json_mod

    resolved = await _resolve_readable_events(session_id, current_user["id"])
    if not resolved:
        raise HTTPException(status_code=404, detail="Transcript not found")
    owner_user_id, events = resolved
    await security_audit_service.record_content_read(
        target_type="transcript",
        target_id=session_id,
        actor_user_id=current_user["id"],
        owner_user_id=owner_user_id,
        metadata={"kind": "export"},
    )

    lines: list[str] = []
    for ev in events:
        role = _event_role(ev.get("event_type"))
        if role is None:
            continue
        line: dict = {
            "type": role,
            "message": {"content": ev.get("content") or ""},
            "timestamp": ev["created_at"].isoformat() if ev.get("created_at") else None,
        }
        if ev.get("tool_name"):
            line["tool_name"] = ev["tool_name"]
        lines.append(json_mod.dumps(line, ensure_ascii=False))
    return PlainTextResponse(
        ("\n".join(lines) + ("\n" if lines else "")),
        media_type="application/jsonl",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id}.jsonl"'},
    )


# --- History-import progress ------------------------------------------------
# `stash import-history` runs as a detached local process; these two endpoints
# are how the web app sees it. The CLI reports counts as it uploads, and Home
# polls until the import finishes. State is a single Redis value per scope with
# a TTL, so a dead importer stops reading as "importing" within the hour.

IMPORT_PROGRESS_TTL_SECONDS = 3600


class ImportProgressReport(BaseModel):
    total: int
    done: int
    errors: int
    finished: bool


@router.put("/import-progress")
async def report_import_progress(
    report: ImportProgressReport,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    await _check_write(scope_user_id, current_user["id"])
    await _get_redis().set(
        f"history-import:{scope_user_id}",
        report.model_dump_json(),
        ex=IMPORT_PROGRESS_TTL_SECONDS,
    )
    return {"ok": True}


@router.get("/import-progress")
async def get_import_progress(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
) -> dict:
    """The scope's current history import, or {"progress": null} if none is
    running (never reported, finished long ago, or the TTL expired)."""
    raw = await _get_redis().get(f"history-import:{scope_user_id}")
    if raw is None:
        return {"progress": None}
    return {"progress": json.loads(raw)}


# --- LEGACY path shapes -----------------------------------------------------
# The canonical routes take session_id as a query parameter (the id is the
# developer's own string, slashes included). These aliases keep every
# installed client working — released CLIs and customer backends (Heavi's
# audit trail shows ~1.7k transcript reads/month over API keys) read by the
# old /{session_id} shapes. Registered last so the static routes above win.
# They die with the legacy cutover, alongside session folders.


@router.get("/{session_id}")
async def get_transcript_metadata_legacy(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await get_transcript_metadata(session_id, current_user)


@router.get("/{session_id}/events")
async def get_transcript_events_legacy(
    session_id: str,
    limit: int = Query(..., ge=1),
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    return await get_transcript_events(session_id, limit, offset, current_user)


@router.get("/{session_id}/export.jsonl")
async def export_transcript_jsonl_legacy(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await export_transcript_jsonl(session_id, current_user)
