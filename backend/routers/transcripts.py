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

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from ..auth import get_current_user
from ..database import get_pool
from ..services import (
    memory_service,
    session_folder_service,
    session_service,
    transcript_import,
    user_scope_service,
)

router = APIRouter(prefix="/api/v1/me/transcripts", tags=["transcripts"])

MAX_TRANSCRIPT_SIZE = 50 * 1024 * 1024


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
    session_folder_id: UUID | None = Form(None),
    replace: bool = Form(False),
    current_user: dict = Depends(get_current_user),
):
    """Parse the uploaded JSONL into history_events rows.

    Existing sessions are left alone unless the caller explicitly asks to
    replace them.
    """
    owner_user_id = current_user["id"]
    await _check_write(owner_user_id, current_user["id"])
    if not _is_jsonl(file.filename):
        raise HTTPException(status_code=400, detail="Session uploads must be .JSONL files")
    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")
    if (
        session_folder_id is not None
        and not await session_folder_service.can_add_session_to_folder(
            owner_user_id=owner_user_id,
            user_id=current_user["id"],
            folder_id=session_folder_id,
        )
    ):
        raise HTTPException(status_code=404, detail="Session folder not found")

    body = await file.read()
    if len(body) > MAX_TRANSCRIPT_SIZE:
        raise HTTPException(status_code=413, detail="Transcript too large (max 50 MB)")

    pool = get_pool()
    existing = await pool.fetchval(
        "SELECT COUNT(*) FROM history_events " "WHERE owner_user_id = $1 AND session_id = $2",
        owner_user_id,
        session_id,
    )
    if existing:
        if not await memory_service.can_read_session(owner_user_id, session_id, current_user["id"]):
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

    if not existing or replace:
        await session_service.upsert_session(
            owner_user_id,
            session_id,
            agent_name=agent_name,
            cwd=cwd,
            created_by=current_user["id"],
            session_folder_id=session_folder_id,
        )

    events = transcript_import.parse_jsonl_to_events(
        body, session_id=session_id, agent_name=agent_name
    )
    if cwd:
        for e in events:
            e["metadata"] = {**(e.get("metadata") or {}), "cwd": cwd}

    inserted = await memory_service.push_events_batch(owner_user_id, current_user["id"], events)
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


@router.get("/{session_id}")
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


@router.get("/{session_id}/events")
async def get_transcript_events(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """One page of chat-thread turns for a session, oldest first, sourced
    directly from history_events. The viewer loads the first page on open and
    fetches more as the reader scrolls. offset is a turn ordinal, so a future
    in-session search can jump straight to a match's window.

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
            return {
                "events": _events_to_viewer_shape(events),
                "total": total,
                "has_more": offset + len(events) < total,
            }
    raise HTTPException(status_code=404, detail="Transcript not found")


@router.get("/{session_id}/export.jsonl")
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
    _, events = resolved

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
