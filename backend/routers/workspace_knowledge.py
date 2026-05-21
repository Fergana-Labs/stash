"""Workspace knowledge router: overview, sessions, files, stashes, and skills."""

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
    files_tree_service,
    llm,
    memory_service,
    session_title_service,
    skill_service,
    stash_service,
    workspace_service,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

SIDEBAR_ETAG_VERSION = "sidebar-event-title-v1"


# ---------------------------------------------------------------------------
# Overview + Sidebar — the per-workspace view shapes
#
# `/overview` is what the workspace home page loads: sessions + files + stashes. `/sidebar`
# is a smaller payload for the nav tree, served with an ETag so it can be
# cached cheaply across navigation.
# ---------------------------------------------------------------------------


async def _list_sessions(workspace_id: UUID, user_id: UUID) -> list[dict]:
    """Sessions in this workspace, sourced from history_events rows."""
    sessions = await memory_service.list_workspace_sessions(workspace_id, user_id)
    return [
        {
            "id": s["id"],
            "session_id": s["session_id"],
            "title": _auto_session_title(s),
            "user_name": s["user_name"],
            "agent_name": s["agent_name"] or "",
            "size_bytes": int(s["size_bytes"] or 0),
            "last_at": s["last_at"],
            "updated_at": s["last_at"],
        }
        for s in sessions
    ]


def _auto_session_title(session: dict) -> str:
    return session_title_service.title_from_text(
        session.get("title_source"),
        session["session_id"],
    )


async def _files_tree(workspace_id: UUID, user_id: UUID) -> dict:
    """One unified file tree: folders, pages, and uploaded files."""
    pool = get_pool()
    folder_rows, page_rows, file_rows = await asyncio.gather(
        pool.fetch(
            "SELECT f.id, f.name, f.parent_folder_id, "
            "       (SELECT COUNT(*) FROM pages p WHERE p.folder_id = f.id "
            "        AND COALESCE(p.metadata->>'shared_in_stash_id', '') = '' "
            "        AND p.deleted_at IS NULL) AS page_count, "
            "       (SELECT COUNT(*) FROM files fi WHERE fi.folder_id = f.id "
            "        AND fi.deleted_at IS NULL) AS file_count, "
            "       EXISTS(SELECT 1 FROM pages p WHERE p.folder_id = f.id AND p.name = 'SKILL.md' "
            "              AND COALESCE(p.metadata->>'shared_in_stash_id', '') = '' "
            "              AND p.deleted_at IS NULL) AS has_skill "
            "FROM folders f WHERE f.workspace_id = $1 ORDER BY f.name",
            workspace_id,
        ),
        pool.fetch(
            "SELECT id, name, content_type, folder_id FROM pages WHERE workspace_id = $1 "
            "AND COALESCE(metadata->>'shared_in_stash_id', '') = '' "
            "AND deleted_at IS NULL ORDER BY name",
            workspace_id,
        ),
        pool.fetch(
            "SELECT id, name, folder_id, size_bytes, content_type, "
            "       created_at, linked_table_id "
            "FROM files WHERE workspace_id = $1 AND deleted_at IS NULL "
            "ORDER BY created_at DESC",
            workspace_id,
        ),
    )

    folders = await files_tree_service._filter_readable(
        [dict(r) for r in folder_rows],
        "folder",
        user_id,
        workspace_id,
    )
    pages = await files_tree_service._filter_readable(
        [dict(r) for r in page_rows],
        "page",
        user_id,
        workspace_id,
    )
    files = await files_tree_service._filter_readable(
        [dict(r) for r in file_rows],
        "file",
        user_id,
        workspace_id,
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
        for f in files
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
            for r in folders
        ],
        "pages": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "content_type": r["content_type"],
                "folder_id": str(r["folder_id"]) if r["folder_id"] else None,
            }
            for r in pages
        ],
        "files": file_payload,
    }


async def _list_stashes(workspace_id: UUID, user_id: UUID) -> list[dict]:
    stashes = await stash_service.list_workspace_stashes(workspace_id, user_id)
    return [
        {
            "id": str(stash["id"]),
            "workspace_id": str(stash["workspace_id"]),
            "slug": stash["slug"],
            "title": stash["title"],
            "description": stash["description"],
            "access": stash["access"],
            "workspace_permission": stash["workspace_permission"],
            "public_permission": stash["public_permission"],
            "discoverable": stash["discoverable"],
            "is_external": stash["is_external"],
            "item_count": len(stash.get("items", [])),
            "items": [
                {
                    "object_type": item["object_type"],
                    "object_id": str(item["object_id"]),
                    "position": item["position"],
                    "label_override": item.get("label_override"),
                }
                for item in stash.get("items", [])
            ],
            "updated_at": stash["updated_at"],
        }
        for stash in stashes
    ]


# ---------------------------------------------------------------------------
# Skills (Phase 2) — markdown folders with a SKILL.md frontmatter file
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/skills")
async def list_workspace_skills(workspace_id: UUID, current_user: dict = Depends(get_current_user)):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    return await skill_service.list_skills(workspace_id, current_user["id"])


@router.get("/{workspace_id}/skills/{name}")
async def get_workspace_skill(
    workspace_id: UUID, name: str, current_user: dict = Depends(get_current_user)
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    skill = await skill_service.read_skill(workspace_id, name, current_user["id"])
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


# ---------------------------------------------------------------------------
# Memory-demo: tailored before/after copy for the Memory onboarding path
# ---------------------------------------------------------------------------


class MemoryDemoResponse(BaseModel):
    topic: str
    before_steps: list[str]
    after_step: str
    real: bool  # true if grounded on an actual session; false for fallback


_FALLBACK_DEMO = MemoryDemoResponse(
    topic="the API gateway refactor",
    before_steps=[
        "Paste 3,200 chars from last week's session",
        "Restate the open questions",
        "List the constraints again",
        "Recap what we tried and what didn't work",
        "“OK, now keep going on the API gateway refactor.”",
    ],
    after_step="“Pick up where we left off on the API gateway refactor.”",
    real=False,
)


@router.post("/{workspace_id}/memory-demo", response_model=MemoryDemoResponse)
async def memory_demo(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Generate a personalized before/after demo for the Memory onboarding
    step. If the workspace has session(s), summon Claude (FAST tier) with
    the most recent session's title + a short snippet of its first events;
    otherwise return a canned fallback."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    sessions = await memory_service.list_workspace_sessions(
        workspace_id, current_user["id"]
    )
    if not sessions:
        return _FALLBACK_DEMO

    newest = max(sessions, key=lambda s: s.get("last_at") or "")
    title = session_title_service.title_from_text(
        newest.get("title_source"), newest["session_id"]
    )
    agent = newest.get("agent_name") or "your agent"

    snippet = ""
    events = await memory_service.read_session_events(
        workspace_id, newest["session_id"], current_user["id"]
    )
    user_event_types = {"user_message", "user_prompt", "prompt", "message", "user"}
    if events:
        first_user_prompts = [
            (e.get("content") or "")
            for e in events
            if e.get("event_type") in user_event_types
        ][:2]
        snippet = "\n---\n".join(p[:800] for p in first_user_prompts if p)

    system_prompt = (
        "You write 2-column before/after demo copy for an onboarding screen. "
        "The user has imported their agent session transcripts. The left column "
        "(\"Without memory\") is a 4–6 step list showing the tedious context-"
        "establishing dance the user would do every time they restart their "
        "agent: pasting context, restating constraints, recapping dead ends. "
        "Each step is one short sentence. The right column (\"With Stash\") is "
        "a single short, casual request that references the topic — no "
        "re-explanation. Tone: concrete, dry, no marketing fluff."
    )
    user_prompt = (
        f"Most recent session title: {title}\n"
        f"Agent: {agent}\n"
        f"Recent prompts from this session (truncated):\n{snippet or '(none available)'}\n\n"
        "Return JSON only, matching this shape exactly:\n"
        "{\n"
        '  "topic": "<short noun phrase describing what was being worked on>",\n'
        '  "before_steps": ["step 1", "step 2", ...],\n'
        '  "after_step": "<one short request, in quotes if dialogue>"\n'
        "}"
    )

    try:
        payload = await llm.complete_json(
            prompt=user_prompt, system=system_prompt, max_tokens=600
        )
        topic = str(payload.get("topic") or title)
        before_steps = [str(s) for s in payload.get("before_steps") or []]
        after_step = str(payload.get("after_step") or "")
        if not before_steps or not after_step:
            raise ValueError("missing fields in LLM response")
        return MemoryDemoResponse(
            topic=topic,
            before_steps=before_steps,
            after_step=after_step,
            real=True,
        )
    except Exception:
        # Either Anthropic call failed or JSON shape was wrong. Fall back
        # to the canned demo but seed the topic with the real session
        # title so it still feels somewhat personal.
        return MemoryDemoResponse(
            topic=title,
            before_steps=[s.replace("the API gateway refactor", title) for s in _FALLBACK_DEMO.before_steps],
            after_step=_FALLBACK_DEMO.after_step.replace("the API gateway refactor", title),
            real=False,
        )


@router.get("/{workspace_id}/overview")
async def get_workspace_overview(
    workspace_id: UUID, current_user: dict = Depends(get_current_user)
):
    """{sessions, files, stashes} for the workspace home page.

    `files` is the flat folder + page + file row set; the frontend builds the tree
    from parent_folder_id.
    """
    await _check_overview_access(workspace_id, current_user["id"])

    sessions, files, stashes = await asyncio.gather(
        _list_sessions(workspace_id, current_user["id"]),
        _files_tree(workspace_id, current_user["id"]),
        _list_stashes(workspace_id, current_user["id"]),
    )
    return {"sessions": sessions, "files": files, "stashes": stashes}


@router.get("/{workspace_id}/sidebar")
async def get_workspace_sidebar(
    workspace_id: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lighter payload for the nav sidebar: sessions + files + stashes. Carries an
    ETag derived from the workspace's mutation timestamps so navigation
    between workspaces hits 304 instead of re-fetching."""
    await _check_overview_access(workspace_id, current_user["id"])

    etag = await _sidebar_etag(workspace_id, current_user["id"])
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    sessions, files, stashes = await asyncio.gather(
        _list_sessions(workspace_id, current_user["id"]),
        _files_tree(workspace_id, current_user["id"]),
        _list_stashes(workspace_id, current_user["id"]),
    )
    return Response(
        content=json.dumps(
            {"sessions": sessions, "files": files, "stashes": stashes},
            default=_json_default,
        ),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "private, max-age=15"},
    )


async def _check_overview_access(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=404, detail="Workspace not found")


async def _sidebar_etag(workspace_id: UUID, user_id: UUID) -> str:
    """One short string that changes any time the sidebar's content
    changes. Concatenates last-modified timestamps across the workspace's
    mutating tables."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT
          (SELECT MAX(updated_at) FROM pages
            WHERE workspace_id = $1 AND COALESCE(metadata->>'shared_in_stash_id', '') = ''
            AND deleted_at IS NULL) AS p,
          (SELECT MAX(created_at) FROM files
            WHERE workspace_id = $1 AND deleted_at IS NULL)                       AS f,
          (SELECT MAX(updated_at) FROM folders WHERE workspace_id = $1)          AS d,
          (SELECT MAX(GREATEST(COALESCE(finished_at, started_at), started_at)) FROM sessions
            WHERE workspace_id = $1 AND deleted_at IS NULL)                       AS s,
          (SELECT MAX(he.created_at) FROM history_events he
            WHERE he.workspace_id = $1 AND he.session_id IS NOT NULL
            AND {memory_service.readable_session_event_condition('he', 2)})        AS he,
          (SELECT COUNT(*) FROM history_events he
            WHERE he.workspace_id = $1 AND he.session_id IS NOT NULL
            AND {memory_service.readable_session_event_condition('he', 2)})        AS hc,
          (SELECT MAX(updated_at) FROM stashes WHERE workspace_id = $1)            AS st,
          (SELECT MAX(sm.created_at) FROM stash_members sm
           JOIN stashes s ON s.id = sm.stash_id
           WHERE s.workspace_id = $1 AND sm.user_id = $2)                          AS sm,
          (SELECT updated_at FROM workspaces WHERE id = $1)                       AS w
        """,
        workspace_id,
        user_id,
    )
    raw = "|".join(
        [SIDEBAR_ETAG_VERSION]
        + [str(row[k] or "") for k in ("p", "f", "d", "s", "he", "hc", "st", "sm", "w")]
    )
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
