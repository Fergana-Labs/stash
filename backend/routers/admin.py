"""Admin router: cross-user analytics. Gated by a shared X-Admin-Token header."""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..config import settings
from ..services import admin_analytics_service, cohort_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = settings.ADMIN_PASSWORD
    if not expected:
        raise HTTPException(
            status_code=503, detail="Admin endpoints disabled (ADMIN_PASSWORD unset)"
        )
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


@router.get("/cohorts/engagement", dependencies=[Depends(require_admin_token)])
async def engagement_cohorts(
    bucket: str = Query("month", pattern="^(month|week|rolling_7d)$"),
    mode: str = Query("standard", pattern="^(standard|future)$"),
    max_period: int | None = Query(None, ge=1, le=104),
    events_filter: str = Query("all", pattern="^(all|active)$"),
):
    return await cohort_service.get_engagement_cohorts(
        bucket=bucket,
        mode=mode,
        max_period=max_period,
        events_filter=events_filter,
    )


@router.get("/analytics/summary", dependencies=[Depends(require_admin_token)])
async def analytics_summary(days: int = Query(7, ge=1, le=90)):
    return await admin_analytics_service.get_summary(days=days)


@router.get("/analytics/onboarding-funnel", dependencies=[Depends(require_admin_token)])
async def analytics_onboarding_funnel(
    days: int = Query(30, ge=1, le=180),
    path: str | None = Query(None, pattern="^(migrant|memory|sharing)$"),
):
    return await admin_analytics_service.get_onboarding_funnel(days=days, path=path)


@router.get("/analytics/path-mix", dependencies=[Depends(require_admin_token)])
async def analytics_path_mix(
    days: int = Query(30, ge=1, le=180),
    bucket: str = Query("day", pattern="^(day|week)$"),
):
    return await admin_analytics_service.get_path_mix(days=days, bucket=bucket)


@router.get("/analytics/surface-mix", dependencies=[Depends(require_admin_token)])
async def analytics_surface_mix(
    days: int = Query(30, ge=1, le=180),
    bucket: str = Query("day", pattern="^(day|week)$"),
):
    return await admin_analytics_service.get_surface_mix(days=days, bucket=bucket)


@router.get("/analytics/top-events", dependencies=[Depends(require_admin_token)])
async def analytics_top_events(
    days: int = Query(30, ge=1, le=180),
    limit: int = Query(20, ge=1, le=100),
):
    return await admin_analytics_service.get_top_events(days=days, limit=limit)
