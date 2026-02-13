from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import get_current_user
from ..models import DMCreateRequest, DMListResponse, DMResponse
from ..services import dm_service

router = APIRouter(prefix="/api/v1/dms", tags=["dms"])


@router.post("", response_model=DMResponse, status_code=200)
async def create_or_get_dm(
    req: DMCreateRequest, current_user: dict = Depends(get_current_user)
):
    """Start or get a DM conversation. Idempotent — returns existing DM if one exists."""
    target_user_id = req.user_id

    if target_user_id is None and req.username:
        # Look up user by username
        from ..database import get_pool

        pool = get_pool()
        row = await pool.fetchrow(
            "SELECT id FROM users WHERE name = $1", req.username
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{req.username}' not found",
            )
        target_user_id = row["id"]

    if target_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either user_id or username",
        )

    try:
        dm = await dm_service.get_or_create_dm(current_user["id"], target_user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )

    return dm


@router.get("", response_model=DMListResponse)
async def list_dms(current_user: dict = Depends(get_current_user)):
    """List all DM conversations, sorted by most recent activity."""
    dms = await dm_service.list_dms(current_user["id"])
    return {"dms": dms}
