"""Deck router: HTML/JS/CSS documents within workspaces."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import (
    DeckCreateRequest,
    DeckListResponse,
    DeckResponse,
    DeckShareAnalyticsResponse,
    DeckShareCreateRequest,
    DeckShareListResponse,
    DeckShareResponse,
    DeckShareUpdateRequest,
    DeckUpdateRequest,
    PermissionResponse,
    SetVisibilityRequest,
    ShareRequest,
    ShareResponse,
)
from ..services import deck_service, permission_service, workspace_service

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/decks", tags=["decks"])


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


# --- Deck CRUD ---


@router.post("", response_model=DeckResponse, status_code=201)
async def create_deck(
    workspace_id: UUID, req: DeckCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    deck = await deck_service.create_deck(
        workspace_id, req.name, req.description, req.html_content,
        req.deck_type, current_user["id"],
    )
    return DeckResponse(**deck)


@router.get("", response_model=DeckListResponse)
async def list_decks(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    decks = await deck_service.list_decks(workspace_id)
    return DeckListResponse(decks=[DeckResponse(**d) for d in decks])


@router.get("/{deck_id}", response_model=DeckResponse)
async def get_deck(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    deck = await deck_service.get_deck(deck_id)
    if not deck or deck.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckResponse(**deck)


@router.patch("/{deck_id}", response_model=DeckResponse)
async def update_deck(
    workspace_id: UUID, deck_id: UUID, req: DeckUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    deck = await deck_service.update_deck(
        deck_id, current_user["id"],
        name=req.name, description=req.description, html_content=req.html_content,
    )
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckResponse(**deck)


@router.delete("/{deck_id}", status_code=204)
async def delete_deck(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete decks")
    deleted = await deck_service.delete_deck(deck_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Deck not found")


# --- Share Links ---


@router.post("/{deck_id}/shares", response_model=DeckShareResponse, status_code=201)
async def create_share_link(
    workspace_id: UUID, deck_id: UUID, req: DeckShareCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    share = await deck_service.create_share_link(
        deck_id, current_user["id"],
        name=req.name, require_email=req.require_email,
        passcode=req.passcode, allow_download=req.allow_download,
        expires_at=req.expires_at,
    )
    return DeckShareResponse(**share)


@router.get("/{deck_id}/shares", response_model=DeckShareListResponse)
async def list_share_links(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    shares = await deck_service.list_share_links(deck_id)
    return DeckShareListResponse(shares=[DeckShareResponse(**s) for s in shares])


@router.delete("/{deck_id}/shares/{share_id}", status_code=204)
async def deactivate_share_link(
    workspace_id: UUID, deck_id: UUID, share_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await deck_service.deactivate_share_link(share_id)


@router.put("/{deck_id}/shares/{share_id}", response_model=DeckShareResponse)
async def update_share_link(
    workspace_id: UUID, deck_id: UUID, share_id: UUID,
    req: DeckShareUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    share = await deck_service.update_share_link(
        share_id, name=req.name, is_active=req.is_active,
        require_email=req.require_email, passcode=req.passcode,
        clear_passcode=req.clear_passcode, allow_download=req.allow_download,
        expires_at=req.expires_at, clear_expires=req.clear_expires,
    )
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found")
    return DeckShareResponse(**share)


@router.get("/{deck_id}/shares/{share_id}/analytics", response_model=DeckShareAnalyticsResponse)
async def get_share_analytics(
    workspace_id: UUID, deck_id: UUID, share_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    analytics = await deck_service.get_share_analytics(share_id)
    return DeckShareAnalyticsResponse(**analytics)


# --- Permissions ---


@router.get("/{deck_id}/permissions", response_model=PermissionResponse)
async def get_permissions(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    perms = await permission_service.get_permissions("deck", deck_id)
    return PermissionResponse(**perms)


@router.patch("/{deck_id}/permissions")
async def set_visibility(
    workspace_id: UUID, deck_id: UUID, req: SetVisibilityRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can change visibility")
    await permission_service.set_visibility("deck", deck_id, req.visibility)
    return {"status": "ok", "visibility": req.visibility}


@router.post("/{deck_id}/permissions/share", response_model=ShareResponse)
async def add_share(
    workspace_id: UUID, deck_id: UUID, req: ShareRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can share")
    share = await permission_service.add_share(
        "deck", deck_id, req.user_id, req.permission, current_user["id"],
    )
    from ..database import get_pool
    pool = get_pool()
    user = await pool.fetchrow("SELECT name FROM users WHERE id = $1", req.user_id)
    return ShareResponse(
        user_id=share["user_id"], user_name=user["name"] if user else "",
        permission=share["permission"], granted_by=share["granted_by"],
        created_at=share["created_at"],
    )


@router.delete("/{deck_id}/permissions/share/{user_id}", status_code=204)
async def remove_share(
    workspace_id: UUID, deck_id: UUID, user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can remove shares")
    await permission_service.remove_share("deck", deck_id, user_id)
