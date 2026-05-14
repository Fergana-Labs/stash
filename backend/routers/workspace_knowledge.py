"""Workspace knowledge router: overview, sessions, wiki, and skills."""

import asyncio
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ..auth import get_current_user
from ..database import get_pool
from ..services import (
    ask_service,
    memory_service,
    skill_service,
    workspace_service,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


# ---------------------------------------------------------------------------
# Overview + Sidebar — the per-workspace view shapes
#
# `/overview` is what the workspace home page loads: sessions + wiki. `/sidebar`
# is a smaller payload for the nav tree, served with an ETag so it can be
# cached cheaply across navigation.
# ---------------------------------------------------------------------------


async def _list_sessions(workspace_id: UUID) -> list[dict]:
    """Sessions in this workspace, sourced from history_events rows."""
    sessions = await memory_service.list_workspace_sessions(workspace_id)
    return [
        {
            "id": s["id"],
            "session_id": s["session_id"],
            "title": s["session_id"],
            "agent_name": s["agent_name"] or "",
            "size_bytes": int(s["size_bytes"] or 0),
            "last_at": s["last_at"],
            "updated_at": s["last_at"],
        }
        for s in sessions
    ]


async def _wiki_tree(workspace_id: UUID) -> dict:
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
            workspace_id,
        ),
        pool.fetch(
            "SELECT id, name, folder_id FROM pages WHERE workspace_id = $1 ORDER BY name",
            workspace_id,
        ),
        pool.fetch(
            "SELECT id, name, folder_id, size_bytes, content_type, "
            "       created_at, linked_table_id "
            "FROM files WHERE workspace_id = $1 ORDER BY created_at DESC",
            workspace_id,
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


@router.get("/{workspace_id}/skills")
async def list_workspace_skills(workspace_id: UUID, current_user: dict = Depends(get_current_user)):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    return await skill_service.list_skills(workspace_id)


@router.get("/{workspace_id}/skills/{name}")
async def get_workspace_skill(
    workspace_id: UUID, name: str, current_user: dict = Depends(get_current_user)
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    skill = await skill_service.read_skill(workspace_id, name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


# ---------------------------------------------------------------------------
# Ask-the-workspace agent (Phase 3)
# ---------------------------------------------------------------------------


class AskMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    messages: list[AskMessage]
    scope: str = "workspace"


@router.post("/{workspace_id}/ask")
async def ask_workspace(
    workspace_id: UUID,
    req: AskRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    workspace = await workspace_service.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    convo = [{"role": m.role, "content": m.content} for m in req.messages]

    return StreamingResponse(
        ask_service.stream_ask(workspace_id, workspace["name"], convo, current_user["id"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{workspace_id}/overview")
async def get_workspace_overview(
    workspace_id: UUID, current_user: dict = Depends(get_current_user)
):
    """{sessions, wiki} for the workspace home page.

    `wiki` is the flat folder + page + file row set; the frontend builds the tree
    from parent_folder_id.
    """
    await _check_overview_access(workspace_id, current_user["id"])

    sessions, wiki = await asyncio.gather(
        _list_sessions(workspace_id),
        _wiki_tree(workspace_id),
    )
    return {
        "sessions": sessions,
        "wiki": wiki,
    }


@router.get("/{workspace_id}/sidebar")
async def get_workspace_sidebar(
    workspace_id: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lighter payload for the nav sidebar: just sessions + wiki. Carries an
    ETag derived from the workspace's mutation timestamps so navigation
    between workspaces hits 304 instead of re-fetching."""
    await _check_overview_access(workspace_id, current_user["id"])

    etag = await _sidebar_etag(workspace_id)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    sessions, wiki = await asyncio.gather(
        _list_sessions(workspace_id),
        _wiki_tree(workspace_id),
    )
    return Response(
        content=json.dumps({"sessions": sessions, "wiki": wiki}, default=_json_default),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "private, max-age=15"},
    )


async def _check_overview_access(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=404, detail="Workspace not found")


async def _sidebar_etag(workspace_id: UUID) -> str:
    """One short string that changes any time the sidebar's content
    changes. Concatenates last-modified timestamps across the workspace's
    mutating tables."""
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT
          (SELECT MAX(updated_at) FROM pages WHERE workspace_id = $1)            AS p,
          (SELECT MAX(created_at) FROM files WHERE workspace_id = $1)            AS f,
          (SELECT MAX(updated_at) FROM folders WHERE workspace_id = $1)          AS d,
          (SELECT MAX(GREATEST(finished_at, started_at)) FROM sessions
            WHERE workspace_id = $1)                                              AS s,
          (SELECT updated_at FROM workspaces WHERE id = $1)                       AS w
        """,
        workspace_id,
    )
    raw = "|".join(str(row[k] or "") for k in ("p", "f", "d", "s", "w"))
    return f'W/"{_short_hash(raw)}"'


def _short_hash(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, UUID):
        return str(o)
    raise TypeError(f"not serializable: {type(o)}")
