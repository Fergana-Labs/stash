"""User knowledge router: overview, sessions, files, and shared skills."""

import asyncio
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ..auth import get_current_user
from ..config import settings
from ..database import get_pool
from ..services import (
    ask_service,
    linear_ticket_service,
    llm,
    memory_service,
    permission_service,
    session_title_service,
    skill_service,
    user_scope_service,
)

router = APIRouter(prefix="/api/v1/me", tags=["me"])

SIDEBAR_ETAG_VERSION = "sidebar-skill-folders-v4"


# ---------------------------------------------------------------------------
# Overview + Sidebar — the per-scope view shapes
#
# `/overview` is what the scope home page loads: sessions + files + skills. `/sidebar`
# is a smaller payload for the nav tree, served with an ETag so it can be
# cached cheaply across navigation.
# ---------------------------------------------------------------------------


async def _list_sessions(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """Sessions in this scope, sourced from history_events rows."""
    sessions = await memory_service.list_scope_sessions(owner_user_id, user_id)
    titles = await session_title_service.titles_for_sessions(owner_user_id, sessions)
    return [
        {
            "id": s["id"],
            "session_id": s["session_id"],
            "title": titles[s["session_id"]],
            "linear_tickets": linear_ticket_service.tickets_response(s.get("linear_tickets")),
            "user_name": s["user_name"],
            "agent_name": s["agent_name"] or "",
            "size_bytes": int(s["size_bytes"] or 0),
            "last_at": s["last_at"],
            "updated_at": s["last_at"],
        }
        for s in sessions
    ]


async def _files_tree(owner_user_id: UUID, user_id: UUID) -> dict:
    """One unified file tree: folders, pages, and uploaded files.

    The viewer's read permission is pushed into each SELECT via
    `readable_content_condition`, so a populated scope costs three queries —
    not three queries plus one `check_access` round-trip per folder/page/file.
    """
    pool = get_pool()
    readable_folder = permission_service.readable_content_condition("folder", "f", 2)
    readable_page = permission_service.readable_content_condition("page", "p", 2)
    readable_file = permission_service.readable_content_condition("file", "fi", 2)
    folder_rows, page_rows, file_rows = await asyncio.gather(
        pool.fetch(
            "SELECT f.id, f.name, f.parent_folder_id, "
            "       (SELECT COUNT(*) FROM pages p WHERE p.folder_id = f.id "
            "        AND p.deleted_at IS NULL) AS page_count, "
            "       (SELECT COUNT(*) FROM files fi WHERE fi.folder_id = f.id "
            "        AND fi.deleted_at IS NULL) AS file_count "
            f"FROM folders f WHERE f.owner_user_id = $1 AND {readable_folder} ORDER BY f.name",
            owner_user_id,
            user_id,
        ),
        pool.fetch(
            "SELECT p.id, p.name, p.content_type, p.folder_id FROM pages p "
            f"WHERE p.owner_user_id = $1 AND p.deleted_at IS NULL AND {readable_page} "
            "ORDER BY p.name",
            owner_user_id,
            user_id,
        ),
        pool.fetch(
            "SELECT fi.id, fi.name, fi.folder_id, fi.size_bytes, fi.content_type, "
            "       fi.created_at, fi.linked_table_id "
            f"FROM files fi WHERE fi.owner_user_id = $1 AND fi.deleted_at IS NULL "
            f"AND {readable_file} ORDER BY fi.created_at DESC",
            owner_user_id,
            user_id,
        ),
    )

    hidden = await skill_service.skill_subtree_folder_ids(owner_user_id)
    folder_rows = [r for r in folder_rows if r["id"] not in hidden]
    page_rows = [r for r in page_rows if r["folder_id"] is None or r["folder_id"] not in hidden]
    file_rows = [r for r in file_rows if r["folder_id"] is None or r["folder_id"] not in hidden]

    return {
        "folders": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "parent_folder_id": str(r["parent_folder_id"]) if r["parent_folder_id"] else None,
                "page_count": int(r["page_count"] or 0),
                "file_count": int(r["file_count"] or 0),
            }
            for r in folder_rows
        ],
        "pages": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "content_type": r["content_type"],
                "folder_id": str(r["folder_id"]) if r["folder_id"] else None,
            }
            for r in page_rows
        ],
        "files": [
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
        ],
    }


async def _list_sidebar_skills(owner_user_id: UUID, user_id: UUID) -> list[dict]:
    """Skill folders (+ publish info when shared) for the sidebar/overview."""
    return await skill_service.list_skills(owner_user_id, user_id)


# ---------------------------------------------------------------------------
# Ask-the-scope agent (Phase 3)
# ---------------------------------------------------------------------------


class AskMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    messages: list[AskMessage]
    scope: str = "all"


@router.post("/ask")
async def ask_scope(
    req: AskRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Ask-the-scope is not configured (ANTHROPIC_API_KEY unset).",
        )
    # Single-turn only. Multi-turn ask should ship as session resumption
    # (ClaudeAgentOptions.resume), not as conversation replay through this
    # request shape — see ask_service.stream_ask.
    if len(req.messages) != 1 or req.messages[0].role != "user":
        raise HTTPException(
            status_code=400,
            detail="Ask currently accepts exactly one user message per request.",
        )
    prompt = req.messages[0].content
    scope_name = current_user.get("display_name") or current_user["name"]

    return StreamingResponse(
        ask_service.stream_ask(owner_user_id, scope_name, prompt, current_user["id"]),
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


@router.post("/memory-demo", response_model=MemoryDemoResponse)
async def memory_demo(
    current_user: dict = Depends(get_current_user),
):
    """Generate a personalized before/after demo for the Memory onboarding
    step. If the scope has session(s), summon Claude (FAST tier) with
    the most recent session's title + a short snippet of its first events;
    otherwise return a canned fallback."""
    owner_user_id = current_user["id"]

    sessions = await memory_service.list_scope_sessions(owner_user_id, current_user["id"])
    if not sessions:
        return _FALLBACK_DEMO

    newest = max(sessions, key=lambda s: s.get("last_at") or "")
    title = session_title_service.title_from_text(newest.get("title_source"), newest["session_id"])
    agent = newest.get("agent_name") or "your agent"

    snippet = ""
    events = await memory_service.read_session_events(
        owner_user_id, newest["session_id"], current_user["id"]
    )
    user_event_types = {"user_message", "user_prompt", "prompt", "message", "user"}
    if events:
        first_user_prompts = [
            (e.get("content") or "") for e in events if e.get("event_type") in user_event_types
        ][:2]
        snippet = "\n---\n".join(p[:800] for p in first_user_prompts if p)

    system_prompt = (
        "You write 2-column before/after demo copy for an onboarding screen. "
        "The user has imported their agent session transcripts. The left column "
        '("Without memory") is a 4–6 step list showing the tedious context-'
        "establishing dance the user would do every time they restart their "
        "agent: pasting context, restating constraints, recapping dead ends. "
        'Each step is one short sentence. The right column ("With Stash") is '
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
        payload = await llm.complete_json(prompt=user_prompt, system=system_prompt, max_tokens=600)
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
            before_steps=[
                s.replace("the API gateway refactor", title) for s in _FALLBACK_DEMO.before_steps
            ],
            after_step=_FALLBACK_DEMO.after_step.replace("the API gateway refactor", title),
            real=False,
        )


@router.get("/overview")
async def get_scope_overview(
    current_user: dict = Depends(get_current_user),
):
    """{sessions, files, skills} for the scope home page.

    `files` is the flat folder + page + file row set; the frontend builds the tree
    from parent_folder_id.
    """
    owner_user_id = current_user["id"]
    await _check_overview_access(owner_user_id, current_user["id"])

    sessions, files, skills = await asyncio.gather(
        _list_sessions(owner_user_id, current_user["id"]),
        _files_tree(owner_user_id, current_user["id"]),
        _list_sidebar_skills(owner_user_id, current_user["id"]),
    )
    return {"sessions": sessions, "files": files, "skills": skills}


@router.get("/sidebar")
async def get_scope_sidebar(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lighter payload for the nav sidebar: sessions + files + skills. Carries an
    ETag derived from the scope's mutation timestamps so navigation
    between scopes hits 304 instead of re-fetching."""
    owner_user_id = current_user["id"]
    await _check_overview_access(owner_user_id, current_user["id"])

    etag = await _sidebar_etag(owner_user_id, current_user["id"])
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    sessions, files, skills = await asyncio.gather(
        _list_sessions(owner_user_id, current_user["id"]),
        _files_tree(owner_user_id, current_user["id"]),
        _list_sidebar_skills(owner_user_id, current_user["id"]),
    )
    return Response(
        content=json.dumps(
            {"sessions": sessions, "files": files, "skills": skills},
            default=_json_default,
        ),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "private, max-age=15"},
    )


async def _check_overview_access(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.is_member(owner_user_id, user_id):
        raise HTTPException(status_code=404, detail="Scope not found")


async def _sidebar_etag(owner_user_id: UUID, user_id: UUID) -> str:
    """One short string that changes any time the sidebar's content
    changes. Concatenates last-modified timestamps across the scope's
    mutating tables."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT
          (SELECT MAX(updated_at) FROM pages
            WHERE owner_user_id = $1
            AND deleted_at IS NULL) AS p,
          (SELECT MAX(created_at) FROM files
            WHERE owner_user_id = $1 AND deleted_at IS NULL)                       AS f,
          (SELECT MAX(updated_at) FROM folders WHERE owner_user_id = $1)          AS d,
          (SELECT MAX(GREATEST(COALESCE(finished_at, started_at), started_at))
           FROM sessions sidebar_session
           WHERE sidebar_session.owner_user_id = $1
             AND sidebar_session.deleted_at IS NULL
             AND EXISTS (
               SELECT 1 FROM history_events sidebar_event
               WHERE sidebar_event.owner_user_id = sidebar_session.owner_user_id
                 AND sidebar_event.session_id = sidebar_session.session_id
             ))                                                                   AS s,
          (SELECT MAX(he.created_at) FROM history_events he
            WHERE he.owner_user_id = $1 AND he.session_id IS NOT NULL
            AND {memory_service.readable_session_event_condition('he', 2)})        AS he,
          (SELECT COUNT(*) FROM history_events he
            WHERE he.owner_user_id = $1 AND he.session_id IS NOT NULL
            AND {memory_service.readable_session_event_condition('he', 2)})        AS hc,
          (SELECT MAX(stt.updated_at) FROM session_titles stt
           JOIN sessions stt_session
             ON stt_session.owner_user_id = stt.owner_user_id
            AND stt_session.session_id = stt.session_id
           WHERE stt.owner_user_id = $1
             AND stt_session.deleted_at IS NULL
             AND {memory_service.readable_session_event_condition('stt_session', 2)}) AS tt,
          (SELECT COUNT(*) FROM session_titles stt
           JOIN sessions stt_session
             ON stt_session.owner_user_id = stt.owner_user_id
            AND stt_session.session_id = stt.session_id
           WHERE stt.owner_user_id = $1
             AND stt_session.deleted_at IS NULL
             AND {memory_service.readable_session_event_condition('stt_session', 2)}) AS tc,
          (SELECT MAX(updated_at) FROM skills WHERE owner_user_id = $1)            AS st,
          (SELECT MAX(sh.created_at) FROM shares sh
           WHERE sh.owner_user_id = $1 AND sh.principal_type = 'user'
             AND sh.principal_id = $2)                                            AS sm
        """,
        owner_user_id,
        user_id,
    )
    raw = "|".join(
        [SIDEBAR_ETAG_VERSION]
        + [str(row[k] or "") for k in ("p", "f", "d", "s", "he", "hc", "tt", "tc", "st", "sm")]
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
