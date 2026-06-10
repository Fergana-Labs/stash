"""Public marketing-events router.

Anonymous, IP rate-limited beacons from the www landing pages: one event
per painted-door page view and one per signup, so the messaging test can
be scored from our own data (views and signups per variant) instead of
relying on X's dashboards. Rows land in analytics_events.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..database import get_pool
from ..middleware import limiter
from ..services import analytics_events_service

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])

_POST_LIMIT = "60/minute"
_GET_LIMIT = "30/minute"

_KINDS = {"view", "signup"}
_VARIANTS = {"drive", "wiki", "connect", "assistant"}


class MarketingEvent(BaseModel):
    kind: str = Field(..., pattern=r"^(view|signup)$")
    variant: str = Field(..., min_length=1, max_length=32)
    url: str = Field("", max_length=2048)
    referrer: str = Field("", max_length=2048)


@router.post("/events", status_code=204)
@limiter.limit(_POST_LIMIT)
async def record_marketing_event(request: Request, event: MarketingEvent) -> None:
    # Unknown variants are dropped silently — this is a public endpoint and
    # garbage input shouldn't pollute the test counts or surface errors.
    if event.variant not in _VARIANTS:
        return
    await analytics_events_service.record_event(
        user_id=None,
        surface="marketing",
        event_name=f"marketing.{event.kind}",
        properties={
            "variant": event.variant,
            "url": event.url,
            "referrer": event.referrer,
        },
    )


@router.get("/summary")
@limiter.limit(_GET_LIMIT)
async def marketing_summary(request: Request) -> dict:
    """Views and signups per variant — aggregate counts only."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT properties->>'variant' AS variant,
               event_name,
               count(*) AS n
        FROM analytics_events
        WHERE surface = 'marketing'
        GROUP BY 1, 2
        """
    )
    summary: dict[str, dict[str, int]] = {
        v: {"views": 0, "signups": 0} for v in sorted(_VARIANTS)
    }
    for r in rows:
        variant = r["variant"]
        if variant not in summary:
            continue
        key = "views" if r["event_name"] == "marketing.view" else "signups"
        summary[variant][key] = r["n"]
    return summary
