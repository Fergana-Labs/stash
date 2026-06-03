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
    cartridge_service,
    memory_service,
    session_service,
    transcript_import,
    workspace_service,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/transcripts", tags=["transcripts"])

MAX_TRANSCRIPT_SIZE = 50 * 1024 * 1024


def _is_jsonl(filename: str | None) -> bool:
    if not filename:
        return False
    name = filename.lower()
    return name.endswith(".jsonl") or name.endswith(".jsonl.gz")


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


@router.post("", status_code=201)
async def upload_transcript(
    workspace_id: UUID,
    file: UploadFile,
    session_id: str = Form(...),
    agent_name: str = Form(...),
    cwd: str | None = Form(None),
    default_cartridge_id: UUID | None = Form(None),
    replace: bool = Form(False),
    current_user: dict = Depends(get_current_user),
):
    """Parse the uploaded JSONL into history_events rows.

    Existing sessions are left alone unless the caller explicitly asks to
    replace them.
    """
    await _check_member(workspace_id, current_user["id"])
    if not _is_jsonl(file.filename):
        raise HTTPException(status_code=400, detail="Session uploads must be .JSONL files")
    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")

    body = await file.read()
    if len(body) > MAX_TRANSCRIPT_SIZE:
        raise HTTPException(status_code=413, detail="Transcript too large (max 50 MB)")

    pool = get_pool()
    existing = await pool.fetchval(
        "SELECT COUNT(*) FROM history_events " "WHERE workspace_id = $1 AND session_id = $2",
        workspace_id,
        session_id,
    )
    if existing:
        if not await memory_service.can_read_session(workspace_id, session_id, current_user["id"]):
            raise HTTPException(status_code=404, detail="Transcript not found")
        if replace:
            await pool.execute(
                "DELETE FROM history_events WHERE workspace_id = $1 AND session_id = $2",
                workspace_id,
                session_id,
            )
        else:
            await session_service.upsert_session(
                workspace_id,
                session_id,
                agent_name=agent_name,
                cwd=cwd,
                created_by=current_user["id"],
            )
            if default_cartridge_id:
                try:
                    await cartridge_service.add_sessions_to_cartridge(
                        cartridge_id=default_cartridge_id,
                        workspace_id=workspace_id,
                        user_id=current_user["id"],
                        session_ids=[session_id],
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
            return {
                "session_id": session_id,
                "imported": 0,
                "skipped": True,
                "reason": "session already has events",
            }

    if not existing or replace:
        await session_service.upsert_session(
            workspace_id,
            session_id,
            agent_name=agent_name,
            cwd=cwd,
            created_by=current_user["id"],
        )

    events = transcript_import.parse_jsonl_to_events(
        body, session_id=session_id, agent_name=agent_name
    )
    if cwd:
        for e in events:
            e["metadata"] = {**(e.get("metadata") or {}), "cwd": cwd}

    inserted = await memory_service.push_events_batch(workspace_id, current_user["id"], events)
    if default_cartridge_id:
        try:
            await cartridge_service.add_sessions_to_cartridge(
                cartridge_id=default_cartridge_id,
                workspace_id=workspace_id,
                user_id=current_user["id"],
                session_ids=[session_id],
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {
        "session_id": session_id,
        "imported": len(inserted),
        "skipped": False,
    }


def _event_role(event_type: str | None) -> str | None:
    """user/assistant projection for the session viewer.

    tool_use events fold into 'assistant' so the timeline shows tool calls
    inline with assistant turns instead of dropping them silently."""
    if event_type in ("user_message", "prompt", "user"):
        return "user"
    if event_type in ("assistant_message", "assistant", "tool_use", "tool_call", "tool_result"):
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


@router.get("/{session_id}")
async def get_transcript_metadata(
    workspace_id: UUID,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Metadata-only response. The frontend follows up with /events for
    the bytes."""
    await _check_member(workspace_id, current_user["id"])
    events = await memory_service.read_session_events(workspace_id, session_id, current_user["id"])
    if not events:
        raise HTTPException(status_code=404, detail="Transcript not found")
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
        "workspace_id": str(workspace_id),
        "agent_name": agent_name,
        "event_count": len(events),
        "size_bytes": size_bytes,
        "cwd": cwd or None,
        "started_at": events[0]["created_at"],
        "last_at": events[-1]["created_at"],
    }


@router.get("/{session_id}/events")
async def get_transcript_events(
    workspace_id: UUID,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Chat-thread turns for a session, in render order. Sourced directly
    from history_events — no JSONL serialization round-trip."""
    await _check_member(workspace_id, current_user["id"])
    events = await memory_service.read_session_events(workspace_id, session_id, current_user["id"])
    if not events:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return {"events": _events_to_viewer_shape(events)}


@router.get("/{session_id}/export.jsonl")
async def export_transcript_jsonl(
    workspace_id: UUID,
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """JSONL projection of the session — one event per line."""
    import json as json_mod

    await _check_member(workspace_id, current_user["id"])
    events = await memory_service.read_session_events(workspace_id, session_id, current_user["id"])
    if not events:
        raise HTTPException(status_code=404, detail="Transcript not found")

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
