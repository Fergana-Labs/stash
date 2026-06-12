"""Skills: special folders (SKILL.md) plus their publish records."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..models import (
    ForkSkillRequest,
    PageResponse,
    SkillPublicResponse,
    SkillPublishRequest,
    SkillResponse,
    SkillUpdateRequest,
)
from ..services import (
    security_audit_service,
    shared_skill_service,
    skill_service,
    source_service,
    workspace_service,
)

ws_router = APIRouter(prefix="/api/v1/workspaces", tags=["skills"])
public_router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

_PUBLIC_ITEM_TYPES = {"page", "file", "table", "folder"}


async def _require_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


@ws_router.post("/{workspace_id}/skills", response_model=SkillResponse, status_code=201)
async def publish_skill(
    workspace_id: UUID,
    req: SkillPublishRequest,
    current_user: dict = Depends(get_current_user),
):
    """Mint the publish record for a skill folder (share/publish it)."""
    await _require_member(workspace_id, current_user["id"])
    try:
        skill = await shared_skill_service.publish_folder(
            workspace_id,
            current_user["id"],
            req.folder_id,
            title=req.title,
            description=req.description,
            discoverable=req.discoverable,
            cover_image_url=req.cover_image_url,
            icon_url=req.icon_url,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SkillResponse(**skill)


@ws_router.get("/{workspace_id}/skills")
async def list_skills(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Every skill folder in the workspace, with publish info when shared."""
    await _require_member(workspace_id, current_user["id"])
    skills = await skill_service.list_skills(workspace_id, current_user["id"])
    return {"skills": skills}


@ws_router.get("/{workspace_id}/skills/{name}")
async def get_local_skill(
    workspace_id: UUID,
    name: str,
    current_user: dict = Depends(get_current_user),
):
    """Read a skill by name: SKILL.md + sibling files concatenated."""
    await _require_member(workspace_id, current_user["id"])
    skill = await skill_service.read_skill(workspace_id, name, current_user["id"])
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


me_router = APIRouter(prefix="/api/v1/me", tags=["skills"])


@me_router.get("/shared-skills")
async def list_shared_skills_with_me(current_user: dict = Depends(get_current_user)):
    """Skill folders shared with me person-to-person (folder shares whose
    folder contains a SKILL.md), with publish info when published."""
    skills = await shared_skill_service.list_skills_shared_with_user(current_user["id"])
    return {"skills": skills}


class SnapshotSourceRequest(BaseModel):
    source_id: UUID
    path: str


@ws_router.post(
    "/{workspace_id}/skills/{skill_id}/snapshot-source",
    response_model=PageResponse,
    status_code=201,
)
async def snapshot_source(
    workspace_id: UUID,
    skill_id: UUID,
    req: SnapshotSourceRequest,
    current_user: dict = Depends(get_current_user),
):
    """Copy a point-in-time snapshot of one connected-source document into the
    skill's folder as a page, so the skill stays self-contained and curl-able."""
    await _require_member(workspace_id, current_user["id"])
    skill = await shared_skill_service.get_skill(skill_id)
    if not skill or skill["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    source = await source_service.get_owned_source_in_workspace(
        req.source_id,
        current_user["id"],
        workspace_id,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    try:
        page = await shared_skill_service.snapshot_source_into_skill(
            skill_id, current_user["id"], source=source, path=req.path
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not allowed to edit this skill")
    if page is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    await security_audit_service.record_event(
        action="source.document_snapshotted",
        actor_user_id=current_user["id"],
        workspace_id=workspace_id,
        target_type="source",
        target_id=source["id"],
        provider=source_service.SOURCE_TYPE_PROVIDER.get(source["source_type"]),
        source_type=source["source_type"],
        metadata={
            "ref_hash": security_audit_service.hash_value(req.path),
            "skill_id": str(skill_id),
        },
    )
    return PageResponse(**page)


class MaterializeSessionRequest(BaseModel):
    folder_id: UUID


@ws_router.post(
    "/{workspace_id}/sessions/{session_id}/materialize",
    response_model=PageResponse,
    status_code=201,
)
async def materialize_session(
    workspace_id: UUID,
    session_id: str,
    req: MaterializeSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Freeze a session transcript into a markdown page inside a folder —
    how sessions travel into skills (sessions can't live in folders)."""
    await _require_member(workspace_id, current_user["id"])
    if not await workspace_service.can_write(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Viewers can read but not materialize sessions")
    page = await shared_skill_service.materialize_session_page(
        workspace_id, session_id, req.folder_id, current_user["id"]
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return PageResponse(**page)


@public_router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: UUID,
    req: SkillUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        skill = await shared_skill_service.update_skill(
            skill_id,
            current_user["id"],
            req.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(**skill)


@public_router.delete("/{skill_id}", status_code=204)
async def unpublish_skill(
    skill_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Delete the publish record (stop sharing). The folder stays a skill;
    delete the folder through the Files API to delete the skill itself."""
    deleted = await shared_skill_service.unpublish_skill(skill_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found")


@public_router.get("/{slug}")
async def get_public_skill(
    slug: str,
    format: str = Query(None, alias="format"),
    current_user: dict | None = Depends(get_current_user_optional),
):
    viewer_id = current_user["id"] if current_user else None
    skill = await shared_skill_service.get_public_skill(slug, viewer_id=viewer_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    contents = await shared_skill_service.folder_contents(skill, viewer_id=viewer_id)

    workspace_name = skill.pop("_workspace_name", "")
    folder_name = skill.pop("_folder_name", "")
    if format == "text":
        return PlainTextResponse(
            shared_skill_service.skill_to_text(
                skill,
                workspace_name,
                contents,
                settings.PUBLIC_URL.rstrip(),
            ),
            media_type="text/markdown",
        )

    can_write = bool(
        current_user and await shared_skill_service.user_can_write(skill["id"], current_user["id"])
    )
    return SkillPublicResponse(
        skill=SkillResponse(**skill),
        workspace_name=workspace_name,
        folder_name=folder_name,
        contents=contents,
        can_write=can_write,
    )


@public_router.get("/{slug}/items/{object_type}/{object_id}")
async def get_public_skill_item(
    slug: str,
    object_type: str,
    object_id: UUID,
    format: str = Query(None, alias="format"),
    current_user: dict | None = Depends(get_current_user_optional),
):
    if object_type not in _PUBLIC_ITEM_TYPES:
        raise HTTPException(status_code=404, detail="Skill item not found")

    viewer_id = current_user["id"] if current_user else None
    skill = await shared_skill_service.get_public_skill(slug, viewer_id=viewer_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    contents = await shared_skill_service.folder_contents(skill, viewer_id=viewer_id)
    item = shared_skill_service.find_in_contents(contents, object_type, str(object_id))
    if not item:
        raise HTTPException(status_code=404, detail="Skill item not found")

    workspace_name = skill.pop("_workspace_name", "")
    skill.pop("_folder_name", "")
    if format == "text":
        return PlainTextResponse(
            shared_skill_service.item_to_text(
                skill, object_type, item, settings.PUBLIC_URL.rstrip()
            ),
            media_type="text/markdown",
        )

    can_write = bool(
        current_user and await shared_skill_service.user_can_write(skill["id"], current_user["id"])
    )
    return {
        "skill": SkillResponse(**skill),
        "workspace_name": workspace_name,
        "object_type": object_type,
        "item": item,
        "can_write": can_write,
    }


@public_router.post("/{slug}/add-to-workspace", status_code=201)
async def fork_skill(
    slug: str,
    req: ForkSkillRequest,
    current_user: dict = Depends(get_current_user),
):
    """Fork: deep-copy the skill's folder into the caller's workspace."""
    await _require_member(req.workspace_id, current_user["id"])
    # Forking writes new pages/files/sessions into the workspace — same bar as
    # creating a Skill.
    if not await workspace_service.can_write(req.workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Viewers can read but not create Skills")
    forked = await shared_skill_service.fork_skill(req.workspace_id, slug, current_user["id"])
    if not forked:
        raise HTTPException(status_code=404, detail="Skill not found")
    return forked
