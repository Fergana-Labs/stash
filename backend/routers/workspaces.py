"""Workspace router: CRUD, membership, invite codes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, get_current_user_optional
from ..models import (
    InviteTokenCreateRequest,
    InviteTokenCreateResponse,
    InviteTokenListResponse,
    InviteTokenSummary,
    RedeemInviteAuthedRequest,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceMember,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from ..config import settings
from ..services import invite_token_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


async def _serialize_workspace_for_viewer(
    workspace: dict, viewer_id: UUID | None
) -> WorkspaceResponse:
    is_member = bool(viewer_id and await workspace_service.is_member(workspace["id"], viewer_id))
    if not is_member:
        # Self-hosted (password auth): auto-join authenticated users to any workspace.
        if viewer_id and not settings.AUTH0_ENABLED:
            await workspace_service.join_workspace(workspace["id"], viewer_id)
        else:
            raise HTTPException(status_code=404, detail="Workspace not found")

    data = dict(workspace)
    return WorkspaceResponse(**data)


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    req: WorkspaceCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.create_workspace(
        name=req.name,
        description=req.description,
        creator_id=current_user["id"],
    )
    return WorkspaceResponse(**ws)


@router.get("/mine", response_model=WorkspaceListResponse)
async def list_my_workspaces(current_user: dict = Depends(get_current_user)):
    workspaces = await workspace_service.list_user_workspaces(current_user["id"])
    return WorkspaceListResponse(workspaces=[WorkspaceResponse(**w) for w in workspaces])


@router.post("/redeem-invite", response_model=WorkspaceResponse)
async def redeem_invite_authed(
    req: RedeemInviteAuthedRequest,
    current_user: dict = Depends(get_current_user),
):
    """Authenticated redeem: join the signed-in user to the workspace."""
    ws = await invite_token_service.redeem_as_existing_user(req.token, current_user["id"])
    if not ws:
        raise HTTPException(
            status_code=404, detail="Invite token is invalid, expired, or exhausted"
        )
    return WorkspaceResponse(**ws)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: dict | None = Depends(get_current_user_optional),
):
    ws = await workspace_service.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    viewer_id = current_user["id"] if current_user else None
    return await _serialize_workspace_for_viewer(ws, viewer_id)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    req: WorkspaceUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_CAN_WRITE:
        raise HTTPException(
            status_code=403, detail="Workspace editors and admins can update workspace"
        )
    ws = await workspace_service.update_workspace(
        workspace_id,
        name=req.name,
        description=req.description,
        cover_image_url=req.cover_image_url,
        icon_url=req.icon_url,
        color_gradient=req.color_gradient,
    )
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse(**ws)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    deleted = await workspace_service.delete_workspace(workspace_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=403, detail="Only workspace admins can delete")


@router.post("/join/{invite_code}", response_model=WorkspaceResponse)
async def join_workspace(
    invite_code: str,
    current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.join_by_invite(invite_code, current_user["id"])
    if not ws:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    return WorkspaceResponse(**ws)


@router.post("/{workspace_id}/invite-code/rotate", response_model=WorkspaceResponse)
async def rotate_invite_code(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    ws = await workspace_service.rotate_invite_code(workspace_id, current_user["id"])
    if not ws:
        raise HTTPException(status_code=403, detail="Only workspace admins can rotate invite code")
    return WorkspaceResponse(**ws)


@router.post("/{workspace_id}/leave", status_code=204)
async def leave_workspace(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    left = await workspace_service.leave_workspace(workspace_id, current_user["id"])
    if not left:
        raise HTTPException(status_code=400, detail="Cannot leave as the last workspace admin")


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMember])
async def get_members(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")
    members = await workspace_service.get_members(workspace_id)
    return [WorkspaceMember(**m) for m in members]


@router.post("/{workspace_id}/members")
async def add_member(
    workspace_id: UUID,
    req: dict,
    current_user: dict = Depends(get_current_user),
):
    """Add a registered user to the workspace by username."""
    if not await workspace_service.is_owner(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Only workspace admins can add members")
    username = req.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    from ..database import get_pool

    pool = get_pool()
    user = await pool.fetchrow("SELECT id FROM users WHERE name = $1", username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    result = await workspace_service.join_workspace(workspace_id, user["id"])
    if not result:
        raise HTTPException(status_code=409, detail="User is already a member")
    return {"status": "ok", "user_id": str(user["id"])}


@router.post("/{workspace_id}/kick/{user_id}", status_code=204)
async def kick_member(
    workspace_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    kicked = await workspace_service.kick_member(workspace_id, user_id, current_user["id"])
    if not kicked:
        raise HTTPException(status_code=403, detail="Cannot kick this member")


class SetRoleRequest(BaseModel):
    role: str  # 'owner' is the product-facing workspace admin role.


@router.patch("/{workspace_id}/members/{user_id}")
async def set_member_role(
    workspace_id: UUID,
    user_id: UUID,
    req: SetRoleRequest,
    current_user: dict = Depends(get_current_user),
):
    """Admin-only: change a member's role."""
    ok = await workspace_service.set_member_role(
        workspace_id, user_id, current_user["id"], req.role
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Couldn't set role — either not admin, invalid role, or last admin",
        )
    return {"status": "ok", "role": req.role}


# ---------------------------------------------------------------------------
# Magic-link invite tokens (distinct from the workspace.invite_code shared secret)
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/invite-tokens", response_model=InviteTokenCreateResponse, status_code=201
)
async def create_invite_token(
    workspace_id: UUID,
    req: InviteTokenCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_ADMIN:
        raise HTTPException(
            status_code=403, detail="Only workspace admins can create invite tokens"
        )
    ws = await workspace_service.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    row, raw = await invite_token_service.create_token(
        workspace_id=workspace_id,
        creator_id=current_user["id"],
        max_uses=req.max_uses,
        ttl_days=req.ttl_days,
    )
    return InviteTokenCreateResponse(
        id=row["id"],
        token=raw,
        workspace_id=row["workspace_id"],
        workspace_name=ws["name"],
        max_uses=row["max_uses"],
        expires_at=row["expires_at"],
    )


@router.get("/{workspace_id}/invite-tokens", response_model=InviteTokenListResponse)
async def list_invite_tokens(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_ADMIN:
        raise HTTPException(status_code=403, detail="Only workspace admins can list invite tokens")
    tokens = await invite_token_service.list_tokens(workspace_id)
    return InviteTokenListResponse(tokens=[InviteTokenSummary(**t) for t in tokens])


@router.delete("/{workspace_id}/invite-tokens/{token_id}", status_code=204)
async def revoke_invite_token(
    workspace_id: UUID,
    token_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in workspace_service.ROLES_ADMIN:
        raise HTTPException(
            status_code=403, detail="Only workspace admins can revoke invite tokens"
        )
    ok = await invite_token_service.revoke_token(token_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Token not found or already revoked")
