"""The home-page feed. Public — a signed-out visitor gets the community
stream (skills + public pages); a signed-in user's feed also resurfaces
items from their own stash."""

from fastapi import APIRouter, Depends

from ..auth import get_current_user_optional
from ..services import feed_service

router = APIRouter(prefix="/api/v1", tags=["feed"])


@router.get("/feed")
async def home_feed(
    cursor: int = 0,
    current_user: dict | None = Depends(get_current_user_optional),
):
    user_id = current_user["id"] if current_user else None
    return await feed_service.home_feed(user_id, max(cursor, 0))
