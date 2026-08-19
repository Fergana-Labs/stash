"""Developer platform: the console API for External Multiplayer.

Self-serve counterpart to the admin workspace endpoints. A user activates the
platform (creating a one-man, invite-only workspace when they have none),
mints machine keys on the workspace's scope user, and manages the orgs their
product's sessions create. Org listing and editing are scope-based like every
other surface: the console sends X-Stash-Scope with the workspace's scope
user id.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import API_KEY_ACCESS_LEVELS, create_api_key, get_current_user, get_scope
from ..services import org_service, permission_service, workspace_service

router = APIRouter(prefix="/api/v1/me/developer", tags=["developer"])
orgs_router = APIRouter(prefix="/api/v1/me/orgs", tags=["developer"])


class ActivateRequest(BaseModel):
    workspace_id: UUID | None = Field(
        None,
        description="Activate on this workspace (must be a member); omit to "
        "create a one-man developer workspace",
    )
    name: str | None = Field(None, max_length=255)


class DeveloperKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    access: str = "read"


class OrgUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    share_wiki: bool | None = None


async def _require_member_workspace(workspace_id: UUID, user_id: UUID) -> dict:
    workspace = await workspace_service.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not await permission_service.is_workspace_member(workspace["scope_user_id"], user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    return workspace


@router.post("/activate")
async def activate_developer_platform(
    req: ActivateRequest, current_user: dict = Depends(get_current_user)
):
    """Turn on the developer platform. With a workspace_id, activates it for
    that workspace; without one, creates a fresh one-man invite-only
    workspace — the solo-developer path."""
    if req.workspace_id is not None:
        workspace = await _require_member_workspace(req.workspace_id, current_user["id"])
    else:
        name = req.name or f"{current_user['display_name'] or current_user['name']} (Developer)"
        workspace = await workspace_service.create_workspace(
            name, domain=None, created_by=current_user["id"]
        )
    return await org_service.activate(workspace["id"], current_user["id"])


@router.post("/keys")
async def mint_developer_key(
    req: DeveloperKeyRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """Mint a machine key on the developer workspace's scope user — the key a
    product backend (e.g. Heavi) uses for every Stash call. Console sends
    X-Stash-Scope to pick the workspace."""
    if req.access not in API_KEY_ACCESS_LEVELS:
        raise HTTPException(status_code=400, detail=f"unknown access level: {req.access}")
    workspace = await org_service.workspace_for_scope(scope_user_id)
    if workspace is None or workspace["external_wiki_folder_id"] is None:
        raise HTTPException(
            status_code=400,
            detail="scope is not an active developer workspace — activate first",
        )
    key = await create_api_key(scope_user_id, name=req.name, key_type="machine", access=req.access)
    return {"workspace_id": str(workspace["id"]), "api_key": key, "access": req.access}


@orgs_router.get("")
async def list_orgs(
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    workspace = await org_service.workspace_for_scope(scope_user_id)
    if workspace is None:
        raise HTTPException(status_code=400, detail="scope is not a workspace")
    orgs = await org_service.list_orgs(workspace["id"])
    stats = (
        await org_service.workspace_stats(workspace)
        if workspace["external_wiki_folder_id"] is not None
        else {"wiki_page_count": 0, "org_session_count": 0}
    )
    return {"workspace": workspace, "orgs": orgs, "stats": stats}


@orgs_router.patch("/{org_id}")
async def update_org(
    org_id: UUID,
    req: OrgUpdateRequest,
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    org = await org_service.get_org(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Org not found")
    workspace = await workspace_service.get_workspace(org["workspace_id"])
    if workspace["scope_user_id"] != scope_user_id:
        raise HTTPException(status_code=403, detail="Org is not in this scope")
    return await org_service.update_org(org_id, name=req.name, share_wiki=req.share_wiki)
