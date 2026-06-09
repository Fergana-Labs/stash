"""Inbound webhooks for push-subscribed sources (Slack today, Granola next).

These endpoints are public — they're called by the provider, not the user — so
they verify the provider's signature and do no heavy work inline: a message
event just enqueues a Celery upsert. Slow handlers get retried/disabled by Slack.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Request

from ..celery_app import celery
from ..config import settings

router = APIRouter(prefix="/api/v1/integrations", tags=["webhooks"])

# Reject replays / stale deliveries beyond Slack's recommended 5-minute window.
SLACK_MAX_SKEW_S = 60 * 5


# --- BEGIN Slack agent (talk-to-Stash bot) — removable feature block ---
# Slack delivers events at-least-once (retries on any non-200/slow ack), so we
# dedupe on event_id before enqueuing an agent reply — otherwise a retry makes
# the bot answer the same question twice.
_redis: aioredis.Redis | None = None
_SLACK_EVENT_TTL_S = 60 * 10


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL)
    return _redis


async def _already_handled(event_id: str | None) -> bool:
    if not event_id:
        return False
    # SET NX returns True only the first time we see this event_id.
    first = await _get_redis().set(f"slack:evt:{event_id}", "1", nx=True, ex=_SLACK_EVENT_TTL_S)
    return not first


def _is_agent_trigger(event: dict) -> bool:
    """True for messages the agent should reply to: @mentions and DMs to the
    bot. Loop guard: never react to the bot's own posts (bot_id) or to
    edits/deletes/joins (subtype). Plain channel messages are ingest-only."""
    if event.get("bot_id") or event.get("subtype"):
        return False
    if event.get("type") == "app_mention":
        return True
    return event.get("type") == "message" and event.get("channel_type") == "im"


# --- END Slack agent ---


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
        team_id = payload.get("team_id")

        # --- BEGIN Slack agent (talk-to-Stash bot) — removable feature block ---
        if _is_agent_trigger(event):
            if not await _already_handled(payload.get("event_id")):
                celery.send_task(
                    "backend.tasks.sources.respond_to_slack_mention",
                    kwargs={"team_id": team_id, "event": event},
                )
            return {"ok": True}
        # --- END Slack agent ---

        # Plain channel messages → existing search ingest (DMs to the bot and
        # @mentions are handled by the agent branch above, not indexed).
        if event.get("type") == "message" and event.get("channel_type") != "im":
            celery.send_task(
                "backend.tasks.sources.ingest_slack_event",
                kwargs={"team_id": team_id, "event": event},
            )
    return {"ok": True}
