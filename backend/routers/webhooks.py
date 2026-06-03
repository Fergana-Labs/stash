"""Inbound webhooks for push-subscribed sources (Slack today, Granola next).

These endpoints are public — they're called by the provider, not the user — so
they verify the provider's signature and do no heavy work inline: a message
event just enqueues a Celery upsert. Slow handlers get retried/disabled by Slack.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException, Request

from ..celery_app import celery
from ..config import settings

router = APIRouter(prefix="/api/v1/integrations", tags=["webhooks"])

# Reject replays / stale deliveries beyond Slack's recommended 5-minute window.
SLACK_MAX_SKEW_S = 60 * 5


def _verify_slack_signature(timestamp: str, body: bytes, signature: str) -> bool:
    secret = settings.SLACK_SIGNING_SECRET
    if not secret or not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > SLACK_MAX_SKEW_S:
            return False
    except ValueError:
        return False
    basestring = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"v0={digest}", signature)


@router.post("/slack/events")
async def slack_events(request: Request):
    body = await request.body()
    if not _verify_slack_signature(
        request.headers.get("X-Slack-Request-Timestamp", ""),
        body,
        request.headers.get("X-Slack-Signature", ""),
    ):
        raise HTTPException(status_code=401, detail="bad signature")

    payload = await request.json()

    # Slack's one-time endpoint verification handshake.
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    if payload.get("type") == "event_callback":
        event = payload.get("event") or {}
        if event.get("type") == "message":
            celery.send_task(
                "backend.tasks.sources.ingest_slack_event",
                kwargs={"team_id": payload.get("team_id"), "event": event},
            )
    return {"ok": True}
