"""Public catalog of Skills — no auth required."""

from fastapi import APIRouter, Query

from ..services import shared_skill_service

router = APIRouter(prefix="/api/v1/discover", tags=["discover"])


@router.get("/skills")
async def list_public_skills(
    q: str | None = Query(None, max_length=128),
    sort: str = Query("trending", pattern="^(trending|newest|popular)$"),
    limit: int = Query(48, ge=1, le=100),
):
    """All Skills whose every item is publicly readable."""
    items = await shared_skill_service.list_public_skills(query=q, sort=sort, limit=limit)
    return {"skills": items}
