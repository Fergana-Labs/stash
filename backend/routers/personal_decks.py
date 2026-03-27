"""Personal decks router: workspace-less HTML/JS/CSS documents."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import (
    DeckCreateRequest,
    DeckListResponse,
    DeckResponse,
    DeckShareCreateRequest,
    DeckShareListResponse,
    DeckShareResponse,
    DeckUpdateRequest,
)
from ..services import deck_service

router = APIRouter(prefix="/api/v1/decks", tags=["personal_decks"])


async def _check_deck_owner(deck_id: UUID, user_id: UUID) -> dict:
    deck = await deck_service.get_deck(deck_id)
    if not deck or deck.get("workspace_id") is not None or deck.get("created_by") != user_id:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


@router.post("", response_model=DeckResponse, status_code=201)
async def create_deck(
    req: DeckCreateRequest, current_user: dict = Depends(get_current_user),
):
    deck = await deck_service.create_deck(
        None, req.name, req.description, req.html_content,
        req.deck_type, current_user["id"],
    )
    return DeckResponse(**deck)


@router.get("", response_model=DeckListResponse)
async def list_decks(current_user: dict = Depends(get_current_user)):
    decks = await deck_service.list_personal_decks(current_user["id"])
    return DeckListResponse(decks=[DeckResponse(**d) for d in decks])


@router.get("/{deck_id}", response_model=DeckResponse)
async def get_deck(deck_id: UUID, current_user: dict = Depends(get_current_user)):
    deck = await _check_deck_owner(deck_id, current_user["id"])
    return DeckResponse(**deck)


@router.patch("/{deck_id}", response_model=DeckResponse)
async def update_deck(
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


@router.delete("/{deck_id}", status_code=204)
async def delete_deck(deck_id: UUID, current_user: dict = Depends(get_current_user)):
    await _check_deck_owner(deck_id, current_user["id"])
    await deck_service.delete_deck(deck_id)


# --- Share Links ---


@router.post("/{deck_id}/shares", response_model=DeckShareResponse, status_code=201)
async def create_share_link(
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


@router.get("/{deck_id}/shares", response_model=DeckShareListResponse)
async def list_share_links(
    deck_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_deck_owner(deck_id, current_user["id"])
    shares = await deck_service.list_share_links(deck_id)
    return DeckShareListResponse(shares=[DeckShareResponse(**s) for s in shares])


@router.delete("/{deck_id}/shares/{share_id}", status_code=204)
async def deactivate_share_link(
    deck_id: UUID, share_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_deck_owner(deck_id, current_user["id"])
    await deck_service.deactivate_share_link(share_id)
