"""Public catalog of Cartridges — no auth required."""

from fastapi import APIRouter, Query

from ..services import cartridge_service

router = APIRouter(prefix="/api/v1/discover", tags=["discover"])


@router.get("/cartridges")
async def list_public_stashes(
    q: str | None = Query(None, max_length=128),
    sort: str = Query("trending", pattern="^(trending|newest|popular)$"),
    limit: int = Query(48, ge=1, le=100),
):
    """All Cartridges whose every item is publicly readable."""
    items = await cartridge_service.list_public_stashes(query=q, sort=sort, limit=limit)
    return {"cartridges": items}
