"""Telemetry ingest: web app + stash CLI POST batched events here.

Auth-only (any logged-in user). The user_id on every row is taken from the
auth context, not the request body — clients cannot impersonate.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import analytics_events_service as svc

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


class EventIn(BaseModel):
    surface: str = Field(..., max_length=16)
    event_name: str = Field(..., max_length=64)
    properties: dict | None = None
    session_anon: str | None = Field(default=None, max_length=64)


class EventBatchRequest(BaseModel):
    events: list[EventIn] = Field(..., max_length=100)


class EventBatchResponse(BaseModel):
    recorded: int


@router.post("/events", response_model=EventBatchResponse)
async def ingest_events(
    body: EventBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    if not body.events:
        return EventBatchResponse(recorded=0)

    rows = []
    for e in body.events:
        if e.surface not in svc.ALLOWED_SURFACES:
            raise HTTPException(status_code=400, detail=f"unknown surface: {e.surface}")
        if e.event_name not in svc.ALLOWED_EVENT_NAMES:
            raise HTTPException(status_code=400, detail=f"unknown event_name: {e.event_name}")
        rows.append(
            {
                "user_id": current_user["id"],
                "surface": e.surface,
                "event_name": e.event_name,
                "properties": e.properties or {},
                "session_anon": e.session_anon,
            }
        )

    recorded = await svc.record_events_batch(rows)
    return EventBatchResponse(recorded=recorded)
