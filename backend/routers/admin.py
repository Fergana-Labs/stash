"""Admin router: cross-user analytics. Gated by a shared X-Admin-Token header."""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..config import settings
from ..services import cohort_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = settings.ADMIN_PASSWORD
    if not expected:
        raise HTTPException(status_code=503, detail="Admin endpoints disabled (ADMIN_PASSWORD unset)")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


@router.get("/cohorts/engagement", dependencies=[Depends(require_admin_token)])
async def engagement_cohorts(
    bucket: str = Query("month", pattern="^(month|week|rolling_7d)$"),
    mode: str = Query("standard", pattern="^(standard|future)$"),
    max_period: int | None = Query(None, ge=1, le=104),
    user_type: str = Query("human", pattern="^(human|persona)$"),
):
    return await cohort_service.get_engagement_cohorts(
        bucket=bucket,
        mode=mode,
        max_period=max_period,
        user_type=user_type,
    )
