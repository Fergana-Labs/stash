"""Stash router — two concepts live here:

1. Workspace-alias endpoints: re-exports workspace CRUD under /api/v1/stashes/*
   with spine, skills, and ask-the-stash.
2. Session-stash endpoints: create/upload/read session snapshots with artifacts
   and transcripts, scoped under workspaces or public by slug.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..database import get_pool
from ..models import (
    InviteTokenCreateRequest,
    InviteTokenCreateResponse,
    InviteTokenListResponse,
    JoinRequestListResponse,
    JoinRequestResponse,
    RedeemInviteAuthedRequest,
    StashArtifactResponse,
    StashCreateRequest,
    StashCreateResponse,
    StashResponse,
    StashUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceForkRequest,
    WorkspaceListResponse,
    WorkspaceMember,
    WorkspacePublicInfo,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from ..services import (
    ask_service,
    handoff_curator,
    memory_service,
    skill_service,
    stash_service,
    storage_service,
    workspace_service,
)
from ..workers import handoff_curator as handoff_curator_worker
from . import workspaces as ws_router_module

# ---------------------------------------------------------------------------
# 1) Workspace-alias router (/api/v1/stashes/*)
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/stashes", tags=["stashes"])

WsStashResponse = WorkspaceResponse
WsStashListResponse = WorkspaceListResponse
WsStashCreateRequest = WorkspaceCreateRequest
WsStashUpdateRequest = WorkspaceUpdateRequest
WsStashForkRequest = WorkspaceForkRequest
WsStashMember = WorkspaceMember
WsStashPublicInfo = WorkspacePublicInfo


@router.post("", response_model=WsStashResponse, status_code=201)
async def create_stash(req: WsStashCreateRequest, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.create_workspace(req, current_user)


@router.get("", response_model=WsStashListResponse)
async def list_stashes(current_user: dict | None = Depends(get_current_user_optional)):
    return await ws_router_module.list_workspaces(current_user)


@router.get("/mine", response_model=WsStashListResponse)
async def list_my_stashes(current_user: dict = Depends(get_current_user)):
    return await ws_router_module.list_my_workspaces(current_user)


@router.post("/redeem-invite", response_model=WsStashResponse)
async def redeem_invite(
    req: RedeemInviteAuthedRequest, current_user: dict = Depends(get_current_user)
):
    return await ws_router_module.redeem_invite_authed(req, current_user)


@router.get("/{stash_id}", response_model=WsStashResponse)
async def get_stash(stash_id: UUID, current_user: dict | None = Depends(get_current_user_optional)):
    return await ws_router_module.get_workspace(stash_id, current_user)


@router.patch("/{stash_id}", response_model=WsStashResponse)
async def update_stash(
    stash_id: UUID, req: WsStashUpdateRequest, current_user: dict = Depends(get_current_user)
):
    return await ws_router_module.update_workspace(stash_id, req, current_user)


@router.delete("/{stash_id}", status_code=204)
async def delete_stash(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    await ws_router_module.delete_workspace(stash_id, current_user)


@router.post("/{stash_id}/fork", response_model=WsStashResponse, status_code=201)
async def fork_stash(
    stash_id: UUID, req: WsStashForkRequest, current_user: dict = Depends(get_current_user)
):
    return await ws_router_module.fork_workspace(stash_id, req, current_user)


@router.post("/join/{invite_code}", response_model=WsStashResponse)
async def join_stash(invite_code: str, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.join_workspace(invite_code, current_user)


@router.post("/{stash_id}/invite-code/rotate", response_model=WsStashResponse)
async def rotate_stash_invite_code(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.rotate_invite_code(stash_id, current_user)


@router.post("/{stash_id}/leave", status_code=204)
async def leave_stash(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    await ws_router_module.leave_workspace(stash_id, current_user)


@router.get("/{stash_id}/members", response_model=list[WsStashMember])
async def get_stash_members(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.get_members(stash_id, current_user)


@router.post("/{stash_id}/members")
async def add_stash_member(
    stash_id: UUID, req: dict, current_user: dict = Depends(get_current_user)
):
    return await ws_router_module.add_member(stash_id, req, current_user)


@router.post("/{stash_id}/kick/{user_id}", status_code=204)
async def kick_stash_member(
    stash_id: UUID, user_id: UUID, current_user: dict = Depends(get_current_user)
):
    await ws_router_module.kick_member(stash_id, user_id, current_user)


@router.get("/{stash_id}/public-info", response_model=WsStashPublicInfo)
async def get_stash_public_info(stash_id: UUID):
    return await ws_router_module.get_workspace_public_info(stash_id)


@router.post("/{stash_id}/join-requests", response_model=JoinRequestResponse, status_code=201)
async def create_stash_join_request(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.create_join_request(stash_id, current_user)


@router.get("/{stash_id}/join-requests", response_model=JoinRequestListResponse)
async def list_stash_join_requests(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.list_join_requests(stash_id, current_user)


@router.post("/{stash_id}/join-requests/{request_id}/approve", response_model=JoinRequestResponse)
async def approve_stash_join_request(
    stash_id: UUID, request_id: UUID, current_user: dict = Depends(get_current_user)
):
    return await ws_router_module.approve_join_request(stash_id, request_id, current_user)


@router.post("/{stash_id}/join-requests/{request_id}/deny", response_model=JoinRequestResponse)
async def deny_stash_join_request(
    stash_id: UUID, request_id: UUID, current_user: dict = Depends(get_current_user)
):
    return await ws_router_module.deny_join_request(stash_id, request_id, current_user)


@router.get("/{stash_id}/join-requests/mine", response_model=JoinRequestResponse)
async def get_my_stash_join_request(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.get_my_join_request(stash_id, current_user)


@router.post("/{stash_id}/invite-tokens", response_model=InviteTokenCreateResponse, status_code=201)
async def create_stash_invite_token(
    stash_id: UUID,
    req: InviteTokenCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    return await ws_router_module.create_invite_token(stash_id, req, current_user)


@router.get("/{stash_id}/invite-tokens", response_model=InviteTokenListResponse)
async def list_stash_invite_tokens(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    return await ws_router_module.list_invite_tokens(stash_id, current_user)


@router.delete("/{stash_id}/invite-tokens/{token_id}", status_code=204)
async def revoke_stash_invite_token(
    stash_id: UUID, token_id: UUID, current_user: dict = Depends(get_current_user)
):
    await ws_router_module.revoke_invite_token(stash_id, token_id, current_user)


# ---------------------------------------------------------------------------
# Spine — the three-folder view (Sessions / Skills / Drive) for one stash
# ---------------------------------------------------------------------------


async def _spine_sessions(stash_id: UUID) -> list[dict]:
    """Sessions in this workspace, sourced from history_events rows."""
    sessions = await memory_service.list_workspace_sessions(stash_id)
    return [
        {
            "session_id": s["session_id"],
            "title": s["session_id"],
            "agent_name": s["agent_name"] or "",
            "size_bytes": int(s["size_bytes"] or 0),
            "last_at": s["last_at"],
            "updated_at": s["last_at"],
        }
        for s in sessions
    ]


async def _spine_wiki(stash_id: UUID) -> dict:
    """One unified Wiki tree — folders, pages, and files for the workspace.

    No Drive/Skill split. A folder is a folder regardless of whether it
    contains a SKILL.md. The frontend builds the tree from parent_folder_id
    and folder_id; the spine is just the flat row set.
    """
    pool = get_pool()
    folder_rows, page_rows, file_rows = await asyncio.gather(
        pool.fetch(
            "SELECT f.id, f.name, f.parent_folder_id, "
            "       (SELECT COUNT(*) FROM pages p WHERE p.folder_id = f.id) AS page_count, "
            "       (SELECT COUNT(*) FROM files fi WHERE fi.folder_id = f.id) AS file_count, "
            "       EXISTS(SELECT 1 FROM pages p WHERE p.folder_id = f.id AND p.name = 'SKILL.md') AS has_skill "
            "FROM folders f WHERE f.workspace_id = $1 ORDER BY f.name",
            stash_id,
        ),
        pool.fetch(
            "SELECT id, name, folder_id FROM pages WHERE workspace_id = $1 ORDER BY name",
            stash_id,
        ),
        pool.fetch(
            "SELECT id, name, folder_id, size_bytes, content_type, "
            "       created_at, linked_table_id "
            "FROM files WHERE workspace_id = $1 ORDER BY created_at DESC",
            stash_id,
        ),
    )

    file_payload = [
        {
            "id": str(f["id"]),
            "name": f["name"],
            "folder_id": str(f["folder_id"]) if f["folder_id"] else None,
            "size_bytes": f["size_bytes"],
            "content_type": f["content_type"],
            "url": None,
            "created_at": f["created_at"],
            "linked_table_id": str(f["linked_table_id"]) if f["linked_table_id"] else None,
        }
        for f in file_rows
    ]

    return {
        "folders": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "parent_folder_id": str(r["parent_folder_id"]) if r["parent_folder_id"] else None,
                "page_count": int(r["page_count"] or 0),
                "file_count": int(r["file_count"] or 0),
                "has_skill": bool(r["has_skill"]),
            }
            for r in folder_rows
        ],
        "pages": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "folder_id": str(r["folder_id"]) if r["folder_id"] else None,
            }
            for r in page_rows
        ],
        "files": file_payload,
    }


# ---------------------------------------------------------------------------
# Skills (Phase 2) — markdown folders with a SKILL.md frontmatter file
# ---------------------------------------------------------------------------


@router.get("/{stash_id}/skills")
async def list_stash_skills(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    if not await workspace_service.is_member(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a stash member")
    return await skill_service.list_skills(stash_id)


@router.get("/{stash_id}/skills/{name}")
async def get_stash_skill(
    stash_id: UUID, name: str, current_user: dict = Depends(get_current_user)
):
    if not await workspace_service.is_member(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a stash member")
    skill = await skill_service.read_skill(stash_id, name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


# ---------------------------------------------------------------------------
# Ask-the-stash agent (Phase 3)
# ---------------------------------------------------------------------------


class AskMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    messages: list[AskMessage]
    scope: str = "stash"


@router.post("/{stash_id}/ask")
async def ask_stash(
    stash_id: UUID,
    req: AskRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a stash member")
    stash = await workspace_service.get_workspace(stash_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    convo = [{"role": m.role, "content": m.content} for m in req.messages]

    return StreamingResponse(
        ask_service.stream_ask(stash_id, stash["name"], convo),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{stash_id}/spine")
async def get_stash_spine(stash_id: UUID, current_user: dict = Depends(get_current_user)):
    """Returns {handoff, sessions, wiki} for the stash home + sidebar tree.

    `wiki` is one shape: {folders, pages, files}. All rows carry their
    parent_folder_id / folder_id so the frontend can build a tree.
    `handoff` is a small envelope; the body is fetched separately via
    /{stash_id}/handoff so the spine response stays small."""
    if not await workspace_service.is_member(stash_id, current_user["id"]):
        ws = await workspace_service.get_workspace(stash_id)
        if not ws or not ws.get("is_public"):
            raise HTTPException(status_code=404, detail="Stash not found")

    sessions, wiki, handoff = await asyncio.gather(
        _spine_sessions(stash_id),
        _spine_wiki(stash_id),
        handoff_curator.get_handoff_summary(stash_id),
    )
    handoff_summary = {
        "present": bool(handoff and handoff["body_markdown"]),
        "generated_at": (
            handoff["generated_at"].isoformat() if handoff and handoff["generated_at"] else None
        ),
        "stale": bool(handoff["stale"]) if handoff else False,
        "pinned_at": handoff["pinned_at"].isoformat() if handoff and handoff["pinned_at"] else None,
    }
    return {"handoff": handoff_summary, "sessions": sessions, "wiki": wiki}


# --- Handoff endpoints ----------------------------------------------------


class HandoffEditRequest(BaseModel):
    body_markdown: str


def _handoff_to_response(row: dict | None) -> dict:
    if row is None:
        return {
            "body_markdown": "",
            "generated_at": None,
            "stale": True,
            "model": None,
            "input_tokens": None,
            "output_tokens": None,
            "turns_used": None,
            "tool_calls_used": None,
            "pinned_at": None,
            "pinned_by": None,
            "last_error": None,
        }
    return {
        "body_markdown": row["body_markdown"],
        "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
        "stale": bool(row["stale"]),
        "model": row["model"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "turns_used": row["turns_used"],
        "tool_calls_used": row["tool_calls_used"],
        "pinned_at": row["pinned_at"].isoformat() if row["pinned_at"] else None,
        "pinned_by": str(row["pinned_by"]) if row["pinned_by"] else None,
        "last_error": row["last_error"],
    }


async def _check_handoff_member(stash_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(stash_id, user_id):
        ws = await workspace_service.get_workspace(stash_id)
        if not ws or not ws.get("is_public"):
            raise HTTPException(status_code=404, detail="Stash not found")


@router.get("/{stash_id}/handoff")
async def get_handoff(
    stash_id: UUID,
    wait: bool = Query(False),
    max_wait: int = Query(60),
    current_user: dict = Depends(get_current_user),
):
    await _check_handoff_member(stash_id, current_user["id"])

    if wait:
        existing = await handoff_curator.get_handoff(stash_id)
        if existing and existing["pinned_at"]:
            return _handoff_to_response(existing)
        # Force a regen now and block until it lands.
        await handoff_curator.force_mark_stale_now(stash_id)
        try:
            await asyncio.wait_for(
                handoff_curator_worker.force_regenerate(stash_id),
                timeout=float(max_wait),
            )
        except TimeoutError:
            pass  # Fall through and return whatever's persisted

    row = await handoff_curator.get_handoff(stash_id)
    return _handoff_to_response(row)


@router.post("/{stash_id}/handoff/refresh", status_code=202)
async def refresh_handoff(
    stash_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.can_write(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to refresh handoff")
    existing = await handoff_curator.get_handoff(stash_id)
    if existing and existing["pinned_at"]:
        raise HTTPException(
            status_code=409,
            detail="Handoff is pinned. Unpin before regenerating.",
        )
    await handoff_curator.force_mark_stale_now(stash_id)
    return {"queued": True}


@router.patch("/{stash_id}/handoff")
async def edit_handoff(
    stash_id: UUID,
    req: HandoffEditRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.can_write(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to edit handoff")
    await handoff_curator.edit_and_pin(stash_id, req.body_markdown, current_user["id"])
    row = await handoff_curator.get_handoff(stash_id)
    return _handoff_to_response(row)


@router.post("/{stash_id}/handoff/unpin", status_code=200)
async def unpin_handoff(
    stash_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.can_write(stash_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to unpin handoff")
    await handoff_curator.unpin(stash_id)
    row = await handoff_curator.get_handoff(stash_id)
    return _handoff_to_response(row)


# ---------------------------------------------------------------------------
# 2) Session-stash endpoints (create/upload/read session snapshots)
# ---------------------------------------------------------------------------

ws_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/stashes",
    tags=["stashes"],
)
public_router = APIRouter(prefix="/api/v1/stashes", tags=["stashes"])


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


@ws_router.post("", response_model=StashCreateResponse, status_code=201)
async def create_session_stash(
    workspace_id: UUID,
    req: StashCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    stash = await stash_service.create_stash(
        workspace_id=workspace_id,
        session_id=req.session_id,
        created_by=current_user["id"],
        agent_name=req.agent_name,
        cwd=req.cwd,
        files_touched=req.files_touched,
    )
    base = settings.PUBLIC_URL.rstrip("/")
    return StashCreateResponse(
        id=stash["id"],
        slug=stash["slug"],
        url=f"{base}/b/{stash['slug']}",
    )


@public_router.post("/{stash_id}/artifacts", status_code=201)
async def upload_artifact(
    stash_id: UUID,
    file: UploadFile,
    file_path: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    stash = await stash_service.get_stash_by_id(stash_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    if not await workspace_service.is_member(stash["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not storage_service.is_configured():
        raise HTTPException(status_code=503, detail="File storage is not configured")

    content = await file.read()
    MAX_ARTIFACT_SIZE = 1 * 1024 * 1024  # 1MB per file
    if len(content) > MAX_ARTIFACT_SIZE:
        raise HTTPException(status_code=413, detail="Artifact too large (max 1 MB)")

    storage_key = await storage_service.upload_file(
        str(stash["workspace_id"]),
        file.filename or file_path.split("/")[-1],
        content,
        file.content_type or "application/octet-stream",
    )
    # stash_id in this URL is the sessions.id UUID (the target of the
    # session-share link). The artifact attaches to that session.
    artifact = await stash_service.add_artifact(
        session_id=stash_id,
        file_path=file_path,
        storage_key=storage_key,
        size_bytes=len(content),
    )
    return StashArtifactResponse(**artifact)


@public_router.patch("/{stash_id}", response_model=StashResponse)
async def update_session_stash(
    stash_id: UUID,
    req: StashUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    stash = await stash_service.get_stash_by_id(stash_id)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")
    if not await workspace_service.is_member(stash["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    updated = await stash_service.update_stash(
        stash_id,
        summary=req.summary,
    )
    return StashResponse(**updated)


# --- Public read endpoints (no auth required) ---


@public_router.get("/{slug}")
async def get_session_stash(
    slug: str,
    format: str | None = Query(None),
    current_user: dict | None = Depends(get_current_user_optional),
):
    stash = await stash_service.get_stash_by_slug(slug)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    artifacts = await stash_service.list_artifacts(stash["id"])

    if format == "text":
        return PlainTextResponse(
            _stash_to_text(stash, artifacts),
            media_type="text/markdown",
        )

    return {
        **StashResponse(**stash).model_dump(),
        "artifacts": [
            StashArtifactResponse(
                id=a["id"],
                file_path=a["file_path"],
                size_bytes=a["size_bytes"],
                created_at=a["created_at"],
            ).model_dump()
            for a in artifacts
        ],
    }


@public_router.get("/{slug}/files/{artifact_id}")
async def get_stash_artifact(slug: str, artifact_id: UUID):
    artifact = await stash_service.get_artifact(artifact_id)
    if not artifact or artifact["stash_slug"] != slug:
        raise HTTPException(status_code=404, detail="Artifact not found")

    content = await storage_service.download_file(artifact["storage_key"])
    return PlainTextResponse(
        content.decode("utf-8", errors="replace"),
        media_type="text/plain",
    )


def _event_role(event_type: str | None) -> str | None:
    if event_type == "user_message":
        return "user"
    if event_type in ("assistant_message", "tool_use"):
        return "assistant"
    return None


@public_router.get("/{slug}/transcript")
async def get_stash_transcript(slug: str):
    """JSONL projection of the session — one line per history_events row."""
    import json as json_mod

    stash = await stash_service.get_stash_by_slug(slug)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    events = await memory_service.read_session_events(
        stash["workspace_id"],
        stash["session_id"],
    )
    if not events:
        raise HTTPException(status_code=404, detail="Transcript not available")

    lines: list[str] = []
    for ev in events:
        role = _event_role(ev.get("event_type"))
        if role is None:
            continue
        line = {
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
    )


@public_router.get("/{slug}/transcript/messages")
async def get_stash_transcript_messages(slug: str):
    """Structured chat-thread view. Used by the public /b/{slug} viewer."""
    stash = await stash_service.get_stash_by_slug(slug)
    if not stash:
        raise HTTPException(status_code=404, detail="Stash not found")

    events = await memory_service.read_session_events(
        stash["workspace_id"],
        stash["session_id"],
    )
    if not events:
        raise HTTPException(status_code=404, detail="Transcript not available")

    messages = []
    for ev in events:
        role = _event_role(ev.get("event_type"))
        if role is None:
            continue
        text = (ev.get("content") or "").strip()
        if not text:
            continue
        messages.append({"role": role, "text": text})
    return {"messages": messages}


def _stash_to_text(stash: dict, artifacts: list[dict]) -> str:
    base = settings.PUBLIC_URL.rstrip("/")
    lines = [f"# Stash: {stash['slug']}", ""]

    if stash.get("agent_name"):
        lines.append(f"**Agent:** {stash['agent_name']}")
    if stash.get("cwd"):
        lines.append(f"**Directory:** {stash['cwd']}")
    lines.append(f"**Status:** {stash['status']}")
    lines.append(f"**Created:** {stash['created_at']}")
    lines.append("")

    if stash.get("summary"):
        lines.append("## Summary")
        lines.append("")
        lines.append(stash["summary"])
        lines.append("")
    elif stash["status"] in ("live", "summarizing"):
        lines.append("## Summary")
        lines.append("")
        lines.append("_Summary is being generated..._")
        lines.append("")

    if artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for a in artifacts:
            url = f"{base}/api/v1/stashes/{stash['slug']}/files/{a['id']}"
            lines.append(f"- [{a['file_path']}]({url}) ({a['size_bytes']} bytes)")
        lines.append("")

    transcript_url = f"{base}/api/v1/stashes/{stash['slug']}/transcript"
    lines.append("## Transcript")
    lines.append("")
    if stash.get("has_transcript"):
        lines.append(f"Full session transcript: [download]({transcript_url})")
    else:
        lines.append("_Transcript not yet available._")
    lines.append("")

    return "\n".join(lines)
