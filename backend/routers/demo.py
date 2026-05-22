"""Public landing-page demo router.

Anonymous, IP rate-limited endpoints that let a visitor's coding agent
read the canonical Stash skill + KB and publish a personalized HTML
slide deck as a public-unlisted Stash. The visitor never signs in.

Each handler is a thin shim that pins the singleton Demo workspace
and delegates straight into the same service functions used by the
authenticated workspace routers — no parallel implementation.
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..middleware import limiter
from ..models import StashItem
from ..services import (
    demo_content,
    demo_service,
    files_tree_service,
    memory_service,
    session_service,
    stash_service,
)
from ..services.files_tree_service import DuplicatePageName

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

# Rate limits — enough headroom for legitimate Q&A flows from a shared
# office network but tight enough to make scripted abuse uncomfortable.
_GET_LIMIT = "60/minute"
_POST_LIMIT = "10/minute"


# --- Request models ---


class DemoPageCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    html: str = Field(..., min_length=1)
    html_layout: str = Field("fixed-aspect", pattern=r"^(responsive|fixed-aspect)$")


class DemoSessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    transcript: str = Field(..., min_length=1)
    agent_name: str = Field("demo-visitor", min_length=1, max_length=64)


class DemoStashCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field("", max_length=2000)
    items: list[StashItem] = Field(..., min_length=1)


# --- Static reads (skill / about / instructions) ---


@router.get("/start", response_class=PlainTextResponse)
@limiter.limit(_GET_LIMIT)
async def start(request: Request) -> str:
    """The agent's entry-point: full step-by-step instructions."""
    return demo_content.START_INSTRUCTIONS_MARKDOWN


@router.get("/skill", response_class=PlainTextResponse)
@limiter.limit(_GET_LIMIT)
async def skill(request: Request) -> str:
    """Canonical HTML slide-deck skill — same bytes as Skills/slides/SKILL.md."""
    return demo_content.SLIDES_SKILL_MARKDOWN


@router.get("/about", response_class=PlainTextResponse)
@limiter.limit(_GET_LIMIT)
async def about(request: Request) -> str:
    """About-Stash knowledge base used as source of truth for deck content."""
    return demo_content.ABOUT_STASH_MARKDOWN


# --- Writes (page / session / stash) ---


@router.post("/pages", status_code=201)
@limiter.limit(_POST_LIMIT)
async def create_page(request: Request, req: DemoPageCreate) -> dict[str, Any]:
    workspace_id, owner_id = await demo_service.get_demo_workspace()
    name = _unique_page_name(req.title)
    try:
        page = await files_tree_service.create_page(
            workspace_id=workspace_id,
            name=name,
            created_by=owner_id,
            folder_id=None,
            content="",
            content_type="html",
            content_html=req.html,
            html_layout=req.html_layout,
        )
    except DuplicatePageName as e:
        # Extremely unlikely given the random suffix, but surface cleanly.
        raise HTTPException(status_code=409, detail=str(e))
    return {"page_id": page["id"], "name": page["name"]}


@router.post("/sessions", status_code=201)
@limiter.limit(_POST_LIMIT)
async def create_session(request: Request, req: DemoSessionCreate) -> dict[str, Any]:
    workspace_id, owner_id = await demo_service.get_demo_workspace()
    # Random session_id keeps demos isolated within the shared workspace.
    session_id = f"demo-{secrets.token_urlsafe(10)}"
    session = await session_service.upsert_session(
        workspace_id=workspace_id,
        session_id=session_id,
        agent_name=req.agent_name,
        cwd=None,
        created_by=owner_id,
    )
    # Single event captures the full Q&A markdown. The stash inline
    # session renderer will surface it as the session's transcript.
    await memory_service.push_event(
        workspace_id=workspace_id,
        agent_name=req.agent_name,
        event_type="assistant_message",
        content=req.transcript,
        created_by=owner_id,
        session_id=session_id,
        metadata={"demo_title": req.title},
    )
    return {"session_id": session["id"], "session_external_id": session_id}


@router.post("/stashes", status_code=201)
@limiter.limit(_POST_LIMIT)
async def create_stash(request: Request, req: DemoStashCreate) -> dict[str, Any]:
    workspace_id, owner_id = await demo_service.get_demo_workspace()

    items = list(req.items)
    # Auto-attach the canonical KB folder so every demo Stash ships with
    # the slides skill + about-Stash docs the agent used to build it.
    kb_folder_id = await demo_service.get_kb_folder_id()
    if not any(
        item.object_type == "folder" and item.object_id == kb_folder_id
        for item in items
    ):
        items.append(
            StashItem(
                object_type="folder",
                object_id=kb_folder_id,
                position=len(items),
                label_override=demo_content.DEMO_KB_FOLDER_NAME,
            )
        )

    for item in items:
        _validate_item_belongs_to_demo(item, workspace_id)

    try:
        stash = await stash_service.create_stash(
            workspace_id=workspace_id,
            owner_id=owner_id,
            title=req.title,
            description=req.description,
            workspace_permission="none",
            public_permission="read",
            discoverable=False,
            cover_image_url=None,
            icon_url=None,
            items=items,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    base = settings.PUBLIC_URL.rstrip("/")
    return {
        "stash_id": stash["id"],
        "slug": stash["slug"],
        "app_url": f"{base}/stashes/{stash['slug']}",
    }


# --- Helpers ---


def _unique_page_name(title: str) -> str:
    """Append a short random suffix so concurrent demos don't collide.

    Page names are unique per (workspace, folder) — without the suffix
    two visitors named "Sam" would race on the same name.
    """
    suffix = secrets.token_urlsafe(4)[:6].lower()
    base = title.strip()[:200]
    return f"{base} — {suffix}"


async def _validate_item_belongs_to_demo(item: StashItem, workspace_id) -> None:
    """Reject attempts to bundle objects from outside the Demo workspace."""
    from ..services import permission_service

    item_workspace_id = await permission_service.resolve_workspace_id(
        item.object_type, item.object_id
    )
    if item_workspace_id != workspace_id:
        raise HTTPException(
            status_code=400,
            detail="Stash items must be in the demo workspace",
        )
