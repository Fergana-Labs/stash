"""Skills: publishable subsets of a workspace."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..auth import get_current_user, get_current_user_optional
from ..config import settings
from ..database import get_pool
from ..models import (
    ForkSkillRequest,
    PageCreateRequest,
    PageResponse,
    SkillCreateRequest,
    SkillMemberRequest,
    SkillMemberResponse,
    SkillMembersResponse,
    SkillPublicResponse,
    SkillResponse,
    SkillUpdateRequest,
    UserSearchResult,
)
from ..services import (
    permission_service,
    security_audit_service,
    shared_skill_service,
    skill_service,
    source_service,
    workspace_service,
)

ws_router = APIRouter(prefix="/api/v1/workspaces", tags=["skills"])
public_router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

_SKILL_ITEM_TYPES = {"folder", "page", "table", "file", "session"}


async def _require_can_share_item(workspace_id: UUID, item, user_id: UUID) -> None:
    item_workspace_id = await permission_service.resolve_workspace_id(
        item.object_type, item.object_id
    )
    if item_workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="Skill items must be in the workspace")

    can_share = await permission_service.check_access(
        item.object_type,
        item.object_id,
        user_id,
        workspace_id=workspace_id,
        require="write",
    )
    if not can_share:
        raise HTTPException(status_code=403, detail="Not allowed to share one or more items")


@ws_router.post("/{workspace_id}/skills", response_model=SkillResponse, status_code=201)
async def create_skill(
    workspace_id: UUID,
    req: SkillCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not await workspace_service.can_write(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Viewers can read but not create Skills")
    if req.discoverable and req.public_permission == "none":
        raise HTTPException(status_code=400, detail="Discover Skills must be public")
    for item in req.items:
        await _require_can_share_item(workspace_id, item, current_user["id"])
    try:
        skill = await shared_skill_service.create_skill(
            workspace_id=workspace_id,
            owner_id=current_user["id"],
            title=req.title,
            description=req.description,
            workspace_permission=req.workspace_permission,
            public_permission=req.public_permission,
            discoverable=req.discoverable,
            cover_image_url=req.cover_image_url,
            icon_url=req.icon_url,
            items=req.items,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SkillResponse(**skill)


@ws_router.post("/{workspace_id}/skills/publish", status_code=201)
async def publish_skill(
    workspace_id: UUID,
    req: SkillCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a public Skill and return its shareable URL."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    if not req.items:
        raise HTTPException(status_code=400, detail="A shared bundle needs at least one item")
    if req.public_permission == "none":
        raise HTTPException(status_code=400, detail="Published Skills must be public")

    for item in req.items:
        await _require_can_share_item(workspace_id, item, current_user["id"])

    try:
        skill = await shared_skill_service.create_skill(
            workspace_id=workspace_id,
            owner_id=current_user["id"],
            title=req.title,
            description=req.description,
            workspace_permission=req.workspace_permission,
            public_permission=req.public_permission,
            discoverable=req.discoverable,
            cover_image_url=req.cover_image_url,
            icon_url=req.icon_url,
            items=req.items,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    base = settings.PUBLIC_URL.rstrip("/")
    return {
        "skill": SkillResponse(**skill),
        "url": f"{base}/skills/{skill['slug']}",
        "skill_id": skill["id"],
        "skill_slug": skill["slug"],
    }


@ws_router.get("/{workspace_id}/skills")
async def list_skills(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Unified skills list: local SKILL.md folders and shared bundles, one
    array discriminated by `kind`."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    local = await skill_service.list_skills(workspace_id, current_user["id"])
    shared = await shared_skill_service.list_workspace_skills(workspace_id, current_user["id"])
    skills = [{"kind": "local", **skill} for skill in local] + [
        {"kind": "shared", "name": skill["title"], **SkillResponse(**skill).model_dump()}
        for skill in shared
    ]
    skills.sort(key=lambda skill: (skill["name"] or "").lower())
    return {"skills": skills}


@ws_router.get("/{workspace_id}/skills/{name}")
async def get_local_skill(
    workspace_id: UUID,
    name: str,
    current_user: dict = Depends(get_current_user),
):
    """Read a local skill by name: SKILL.md + sibling files concatenated."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    skill = await skill_service.read_skill(workspace_id, name, current_user["id"])
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@ws_router.delete("/{workspace_id}/external-skills/{skill_id}", status_code=204)
async def remove_forked_skill(
    workspace_id: UUID,
    skill_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    deleted = await shared_skill_service.remove_forked_skill(
        workspace_id,
        skill_id,
        current_user["id"],
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Forked Skill not found")


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
    skill as a page, so the bundle stays self-contained and curl-able."""
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
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


@ws_router.get("/{workspace_id}/skills/objects/{object_type}/{object_id}")
async def list_object_skills(
    workspace_id: UUID,
    object_type: str,
    object_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if object_type not in {"folder", "page", "table", "file", "session"}:
        raise HTTPException(status_code=400, detail="Unsupported Skill item type")
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    item_workspace_id = await permission_service.resolve_workspace_id(object_type, object_id)
    if item_workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Object not found")
    skills = await shared_skill_service.list_object_skills(
        workspace_id,
        object_type,
        object_id,
        current_user["id"],
    )
    return {"skills": [SkillResponse(**skill) for skill in skills]}


@public_router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: UUID,
    req: SkillUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await shared_skill_service.user_can_manage(skill_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this skill")
    skill = await shared_skill_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if req.items is not None:
        for item in req.items:
            await _require_can_share_item(skill["workspace_id"], item, current_user["id"])
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
async def delete_skill(
    skill_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await shared_skill_service.user_can_manage(skill_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to manage this skill")
    deleted = await shared_skill_service.delete_skill(skill_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found")


async def _require_can_manage_skill(skill_id: UUID, user_id: UUID) -> dict:
    skill = await shared_skill_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if not await shared_skill_service.user_can_admin(skill_id, user_id):
        raise HTTPException(status_code=403, detail="Not allowed to manage this skill")
    return skill


@public_router.get("/{skill_id}/members", response_model=SkillMembersResponse)
async def list_skill_members(
    skill_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _require_can_manage_skill(skill_id, current_user["id"])
    members = await shared_skill_service.list_members(skill_id)
    return SkillMembersResponse(members=[SkillMemberResponse(**member) for member in members])


@public_router.get("/{skill_id}/member-search", response_model=list[UserSearchResult])
async def search_skill_member_candidates(
    skill_id: UUID,
    q: str = Query(..., min_length=1, max_length=64),
    current_user: dict = Depends(get_current_user),
):
    """Candidate members for the share dialog: the skill's workspace members.
    Authorized by skill admin rights, not workspace membership — a skill admin
    from outside the workspace manages members too."""
    skill = await _require_can_manage_skill(skill_id, current_user["id"])
    rows = await get_pool().fetch(
        "SELECT u.id, u.name, u.display_name "
        "FROM workspace_members wm "
        "JOIN users u ON u.id = wm.user_id "
        "WHERE wm.workspace_id = $1 "
        "AND (u.name ILIKE $2 OR u.display_name ILIKE $2) "
        "AND u.id != $3 "
        "ORDER BY u.display_name, u.name "
        "LIMIT 20",
        skill["workspace_id"],
        f"%{q}%",
        current_user["id"],
    )
    return [UserSearchResult(**dict(r)) for r in rows]


@public_router.post("/{skill_id}/members", response_model=SkillMemberResponse, status_code=201)
async def add_skill_member(
    skill_id: UUID,
    req: SkillMemberRequest,
    current_user: dict = Depends(get_current_user),
):
    skill = await _require_can_manage_skill(skill_id, current_user["id"])

    pool = get_pool()
    user = await pool.fetchrow("SELECT id FROM users WHERE id = $1", req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    target_role = await workspace_service.get_member_role(skill["workspace_id"], req.user_id)
    if target_role is None and not await workspace_service.is_owner(
        skill["workspace_id"], current_user["id"]
    ):
        raise HTTPException(
            status_code=403,
            detail="Only workspace owners can share Skills outside the workspace",
        )
    # Admin grants are fine for externals (admin = manage, never content
    # write — user_can_write stays workspace-bound), but write grants are not.
    if req.permission == "write" and target_role not in workspace_service.ROLES_CAN_WRITE:
        raise HTTPException(
            status_code=403,
            detail="Skill write access requires a workspace editor or owner",
        )

    try:
        member = await shared_skill_service.add_member(
            skill_id,
            req.user_id,
            req.permission,
            current_user["id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not member:
        raise HTTPException(status_code=404, detail="Skill not found")
    await security_audit_service.record_event(
        action="skill.member_granted",
        actor_user_id=current_user["id"],
        workspace_id=skill["workspace_id"],
        target_type="skill",
        target_id=str(skill_id),
        metadata={
            "permission": req.permission,
            "recipient_user_hash": security_audit_service.hash_value(str(req.user_id)),
        },
    )
    return SkillMemberResponse(**member)


@public_router.delete("/{skill_id}/members/{user_id}", status_code=204)
async def remove_skill_member(
    skill_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    skill = await _require_can_manage_skill(skill_id, current_user["id"])
    removed = await shared_skill_service.remove_member(skill_id, user_id)
    if removed:
        await security_audit_service.record_event(
            action="skill.member_removed",
            actor_user_id=current_user["id"],
            workspace_id=skill["workspace_id"],
            target_type="skill",
            target_id=str(skill_id),
            metadata={
                "recipient_user_hash": security_audit_service.hash_value(str(user_id)),
            },
        )


@public_router.post("/{skill_id}/shared-pages", response_model=PageResponse, status_code=201)
async def create_shared_skill_page(
    skill_id: UUID,
    req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        page = await shared_skill_service.create_shared_page(
            skill_id,
            current_user["id"],
            name=req.name,
            content=req.content,
            content_type=req.content_type,
            content_html=req.content_html,
            html_layout=req.html_layout,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not page:
        raise HTTPException(status_code=404, detail="Skill not found")
    return PageResponse(**page)


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
    items = await shared_skill_service.inline_items(skill, viewer_id=viewer_id)

    if format == "text":
        return PlainTextResponse(
            shared_skill_service.skill_to_text(
                skill,
                skill.get("_workspace_name", ""),
                items,
                settings.PUBLIC_URL.rstrip(),
            ),
            media_type="text/markdown",
        )

    workspace_name = skill.pop("_workspace_name", "")
    can_write = bool(
        current_user and await shared_skill_service.user_can_write(skill["id"], current_user["id"])
    )
    return SkillPublicResponse(
        skill=SkillResponse(**skill),
        workspace_name=workspace_name,
        items=items,
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
    if object_type not in _SKILL_ITEM_TYPES:
        raise HTTPException(status_code=404, detail="Skill item not found")

    viewer_id = current_user["id"] if current_user else None
    skill = await shared_skill_service.get_public_skill(slug, viewer_id=viewer_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    items = await shared_skill_service.inline_items(skill, viewer_id=viewer_id)
    item = next(
        (
            candidate
            for candidate in items
            if candidate["object_type"] == object_type
            and str(candidate["object_id"]) == str(object_id)
        ),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Skill item not found")

    if format == "text":
        return PlainTextResponse(
            shared_skill_service.item_to_text(skill, item, settings.PUBLIC_URL.rstrip()),
            media_type="text/markdown",
        )

    workspace_name = skill.pop("_workspace_name", "")
    can_write = bool(
        current_user and await shared_skill_service.user_can_write(skill["id"], current_user["id"])
    )
    return {
        "skill": SkillResponse(**skill),
        "workspace_name": workspace_name,
        "item": item,
        "can_write": can_write,
    }


@public_router.post("/{slug}/add-to-workspace", response_model=SkillResponse, status_code=201)
async def add_skill_to_workspace(
    slug: str,
    req: ForkSkillRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(req.workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    # Forking writes new pages/files/sessions into the workspace — same bar as
    # creating a Skill.
    if not await workspace_service.can_write(req.workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Viewers can read but not create Skills")
    skill = await shared_skill_service.fork_skill(req.workspace_id, slug, current_user["id"])
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(**skill)
