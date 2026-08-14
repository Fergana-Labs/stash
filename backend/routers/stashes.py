"""Stash management: create and name extra isolated scopes, mint agent keys.

All endpoints operate on stashes the caller owns — there is no cross-user
stash administration here (workspaces keep their admin-token endpoints)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import create_api_key, get_current_user
from ..services import stash_service

router = APIRouter(prefix="/api/v1/me/stashes", tags=["stashes"])


class Stash(BaseModel):
    id: UUID
    name: str
    scope_user_id: UUID
    created_at: datetime
    # Sidebar activity facts; absent on create/rename responses, which return
    # the bare row.
    item_count: int = 0
    last_activity_at: datetime | None = None


class StashListResponse(BaseModel):
    stashes: list[Stash]


class StashCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class StashRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class StashKeyCreateRequest(BaseModel):
    name: str = Field(default="agent", min_length=1, max_length=128)


class StashKeyCreateResponse(BaseModel):
    api_key: str
    name: str


@router.get("", response_model=StashListResponse)
async def list_stashes(current_user: dict = Depends(get_current_user)):
    rows = await stash_service.list_for_user(current_user["id"])
    return StashListResponse(stashes=[Stash(**row) for row in rows])


@router.post("", response_model=Stash, status_code=201)
async def create_stash(req: StashCreateRequest, current_user: dict = Depends(get_current_user)):
    try:
        row = await stash_service.create_stash(current_user["id"], req.name.strip())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return Stash(**row)


@router.patch("/{stash_id}", response_model=Stash)
async def rename_stash(
    stash_id: UUID, req: StashRenameRequest, current_user: dict = Depends(get_current_user)
):
    row = await stash_service.rename_stash(stash_id, current_user["id"], req.name.strip())
    if row is None:
        raise HTTPException(status_code=404, detail="Stash not found")
    return Stash(**row)


@router.post("/{stash_id}/keys", response_model=StashKeyCreateResponse, status_code=201)
async def create_stash_key(
    stash_id: UUID, req: StashKeyCreateRequest, current_user: dict = Depends(get_current_user)
):
    """Mint an API key on the stash's scope user. An agent holding this key
    acts inside the stash with no scope header — the credential IS the stash
    selector, same as a workspace machine key. Raw key returned once."""
    stash = await stash_service.get_owned_stash(stash_id, current_user["id"])
    if stash is None:
        raise HTTPException(status_code=404, detail="Stash not found")
    api_key = await create_api_key(
        stash["scope_user_id"], name=req.name, key_type="machine", access="full"
    )
    return StashKeyCreateResponse(api_key=api_key, name=req.name)
