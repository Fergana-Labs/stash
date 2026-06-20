"""Scope accessor (transitional).

The workspace entity is gone — a user IS their own scope. These endpoints just
expose the caller's scope id (their user id) so existing clients/tests can fetch
it. Mounted at the old /workspaces paths for now; folded into /me in a later
stage. There is no creation, update, membership, or branding anymore.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user

router = APIRouter(prefix="/api/v1/workspaces", tags=["scope"])


def _scope(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user.get("display_name") or user["name"],
        "description": "",
        "creator_id": user["id"],
        "invite_code": "",
        "created_at": user["created_at"],
        "updated_at": user.get("last_seen") or user["created_at"],
        "member_count": 1,
        "is_primary": True,
    }


@router.post("", status_code=201)
async def get_or_create_scope(current_user: dict = Depends(get_current_user)):
    return _scope(current_user)


@router.get("/mine")
async def list_my_scope(current_user: dict = Depends(get_current_user)):
    return {"workspaces": [_scope(current_user)]}


@router.get("/{owner_user_id}")
async def get_scope(owner_user_id: UUID, current_user: dict = Depends(get_current_user)):
    if owner_user_id != current_user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    return _scope(current_user)
