"""Deck router: workspace and personal HTML/JS/CSS documents."""

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

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/decks", tags=["decks"])
personal_router = APIRouter(prefix="/api/v1/decks", tags=["personal_decks"])


# --- Shared auth helpers ---


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _check_deck_owner(deck_id: UUID, user_id: UUID) -> dict:
    deck = await deck_service.get_deck(deck_id)
    if not deck or deck.get("workspace_id") is not None or deck.get("created_by") != user_id:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


# ===== Workspace deck endpoints =====


@ws_router.post("", response_model=DeckResponse, status_code=201)
async def create_ws_deck(
    workspace_id: UUID, req: DeckCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    deck = await deck_service.create_deck(
        workspace_id, req.name, req.description, req.html_content,
        req.deck_type, current_user["id"],
    )
    return DeckResponse(**deck)


@ws_router.get("", response_model=DeckListResponse)
async def list_ws_decks(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    decks = await deck_service.list_decks(workspace_id)
    return DeckListResponse(decks=[DeckResponse(**d) for d in decks])


@ws_router.get("/{deck_id}", response_model=DeckResponse)
async def get_ws_deck(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    deck = await deck_service.get_deck(deck_id)
    if not deck or deck.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckResponse(**deck)


async def _check_ws_deck(workspace_id: UUID, deck_id: UUID) -> dict:
    """Verify deck exists and belongs to the given workspace."""
    deck = await deck_service.get_deck(deck_id)
    if not deck or deck.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


@ws_router.patch("/{deck_id}", response_model=DeckResponse)
async def update_ws_deck(
    workspace_id: UUID, deck_id: UUID, req: DeckUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await _check_ws_deck(workspace_id, deck_id)
    deck = await deck_service.update_deck(
        deck_id, current_user["id"],
        name=req.name, description=req.description, html_content=req.html_content,
    )
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckResponse(**deck)


@ws_router.delete("/{deck_id}", status_code=204)
async def delete_ws_deck(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete decks")
    await _check_ws_deck(workspace_id, deck_id)
    deleted = await deck_service.delete_deck(deck_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Deck not found")


# --- Workspace share links ---


@ws_router.post("/{deck_id}/shares", response_model=DeckShareResponse, status_code=201)
async def create_ws_share_link(
    workspace_id: UUID, deck_id: UUID, req: DeckShareCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await _check_ws_deck(workspace_id, deck_id)
    share = await deck_service.create_share_link(
        deck_id, current_user["id"],
        name=req.name, require_email=req.require_email,
        passcode=req.passcode, allow_download=req.allow_download,
        expires_at=req.expires_at,
    )
    return DeckShareResponse(**share)


@ws_router.get("/{deck_id}/shares", response_model=DeckShareListResponse)
async def list_ws_share_links(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await _check_ws_deck(workspace_id, deck_id)
    shares = await deck_service.list_share_links(deck_id)
    return DeckShareListResponse(shares=[DeckShareResponse(**s) for s in shares])


@ws_router.delete("/{deck_id}/shares/{share_id}", status_code=204)
async def deactivate_ws_share_link(
    workspace_id: UUID, deck_id: UUID, share_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await _check_ws_deck(workspace_id, deck_id)
    await deck_service.deactivate_share_link(share_id)


@ws_router.put("/{deck_id}/shares/{share_id}", response_model=DeckShareResponse)
async def update_ws_share_link(
    workspace_id: UUID, deck_id: UUID, share_id: UUID,
    req: DeckShareUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await _check_ws_deck(workspace_id, deck_id)
    share = await deck_service.update_share_link(
        share_id, name=req.name, is_active=req.is_active,
        require_email=req.require_email, passcode=req.passcode,
        clear_passcode=req.clear_passcode, allow_download=req.allow_download,
        expires_at=req.expires_at, clear_expires=req.clear_expires,
    )
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found")
    return DeckShareResponse(**share)


@ws_router.get("/{deck_id}/shares/{share_id}/analytics", response_model=DeckShareAnalyticsResponse)
async def get_ws_share_analytics(
    workspace_id: UUID, deck_id: UUID, share_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await _check_ws_deck(workspace_id, deck_id)
    analytics = await deck_service.get_share_analytics(share_id)
    return DeckShareAnalyticsResponse(**analytics)


# --- Workspace permissions ---


@ws_router.get("/{deck_id}/permissions", response_model=PermissionResponse)
async def get_permissions(
    workspace_id: UUID, deck_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    await _check_ws_deck(workspace_id, deck_id)
    perms = await permission_service.get_permissions("deck", deck_id)
    return PermissionResponse(**perms)


@ws_router.patch("/{deck_id}/permissions")
async def set_visibility(
    workspace_id: UUID, deck_id: UUID, req: SetVisibilityRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can change visibility")
    await _check_ws_deck(workspace_id, deck_id)
    await permission_service.set_visibility("deck", deck_id, req.visibility)
    return {"status": "ok", "visibility": req.visibility}


@ws_router.post("/{deck_id}/permissions/share", response_model=ShareResponse)
async def add_share(
    workspace_id: UUID, deck_id: UUID, req: ShareRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can share")
    await _check_ws_deck(workspace_id, deck_id)
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


@ws_router.delete("/{deck_id}/permissions/share/{user_id}", status_code=204)
async def remove_share(
    workspace_id: UUID, deck_id: UUID, user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can remove shares")
    await _check_ws_deck(workspace_id, deck_id)
    await permission_service.remove_share("deck", deck_id, user_id)


# ===== Personal deck endpoints =====


@personal_router.post("", response_model=DeckResponse, status_code=201)
async def create_personal_deck(
    req: DeckCreateRequest, current_user: dict = Depends(get_current_user),
):
    deck = await deck_service.create_deck(
        None, req.name, req.description, req.html_content,
        req.deck_type, current_user["id"],
    )
    return DeckResponse(**deck)


@personal_router.get("", response_model=DeckListResponse)
async def list_personal_decks(current_user: dict = Depends(get_current_user)):
    decks = await deck_service.list_decks(None, user_id=current_user["id"])
    return DeckListResponse(decks=[DeckResponse(**d) for d in decks])


@personal_router.get("/{deck_id}", response_model=DeckResponse)
async def get_personal_deck(deck_id: UUID, current_user: dict = Depends(get_current_user)):
    deck = await _check_deck_owner(deck_id, current_user["id"])
    return DeckResponse(**deck)


@personal_router.patch("/{deck_id}", response_model=DeckResponse)
async def update_personal_deck(
    deck_id: UUID, req: DeckUpdateRequest, current_user: dict = Depends(get_current_user),
):
    await _check_deck_owner(deck_id, current_user["id"])
    deck = await deck_service.update_deck(
        deck_id, current_user["id"],
        name=req.name, description=req.description, html_content=req.html_content,
    )
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckResponse(**deck)


@personal_router.delete("/{deck_id}", status_code=204)
async def delete_personal_deck(deck_id: UUID, current_user: dict = Depends(get_current_user)):
    await _check_deck_owner(deck_id, current_user["id"])
    await deck_service.delete_deck(deck_id)


# --- Personal share links ---


@personal_router.post("/{deck_id}/shares", response_model=DeckShareResponse, status_code=201)
async def create_personal_share_link(
    deck_id: UUID, req: DeckShareCreateRequest, current_user: dict = Depends(get_current_user),
):
    await _check_deck_owner(deck_id, current_user["id"])
    share = await deck_service.create_share_link(
        deck_id, current_user["id"],
        name=req.name, require_email=req.require_email,
        passcode=req.passcode, allow_download=req.allow_download,
        expires_at=req.expires_at,
    )
    return DeckShareResponse(**share)


@personal_router.get("/{deck_id}/shares", response_model=DeckShareListResponse)
async def list_personal_share_links(
    deck_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_deck_owner(deck_id, current_user["id"])
    shares = await deck_service.list_share_links(deck_id)
    return DeckShareListResponse(shares=[DeckShareResponse(**s) for s in shares])


@personal_router.delete("/{deck_id}/shares/{share_id}", status_code=204)
async def deactivate_personal_share_link(
    deck_id: UUID, share_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_deck_owner(deck_id, current_user["id"])
    await deck_service.deactivate_share_link(share_id)
