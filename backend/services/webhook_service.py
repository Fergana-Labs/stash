"""Webhook service: per-workspace webhooks with event filtering."""

import asyncio
import hashlib
import hmac
import json
import logging
from uuid import UUID

import httpx

from ..database import get_pool

logger = logging.getLogger("boozle")


async def create_webhook(
    workspace_id: UUID, user_id: UUID, url: str,
    secret: str | None = None, event_filter: list[str] | None = None,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO webhooks (workspace_id, user_id, url, secret, event_filter)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (workspace_id, user_id) DO UPDATE
             SET url = EXCLUDED.url,
                 secret = EXCLUDED.secret,
                 event_filter = EXCLUDED.event_filter,
                 is_active = true,
                 updated_at = now()
           RETURNING id, workspace_id, user_id, url, secret, event_filter, is_active, created_at, updated_at""",
        workspace_id, user_id, url, secret, event_filter or [],
    )
    return _row_to_dict(row)


async def get_webhook(workspace_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, user_id, url, secret, event_filter, is_active, created_at, updated_at "
        "FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
        workspace_id, user_id,
    )
    return _row_to_dict(row) if row else None


async def update_webhook(
    workspace_id: UUID, user_id: UUID,
    url: str | None = None, secret: str | None = None,
    event_filter: list[str] | None = None, is_active: bool | None = None,
) -> dict | None:
    sets, args, idx = [], [], 1
    if url is not None:
        sets.append(f"url = ${idx}")
        args.append(url)
        idx += 1
    if secret is not None:
        sets.append(f"secret = ${idx}")
        args.append(secret)
        idx += 1
    if event_filter is not None:
        sets.append(f"event_filter = ${idx}")
        args.append(event_filter)
        idx += 1
    if is_active is not None:
        sets.append(f"is_active = ${idx}")
        args.append(is_active)
        idx += 1
    if not sets:
        return await get_webhook(workspace_id, user_id)
    sets.append("updated_at = now()")
    args.extend([workspace_id, user_id])
    pool = get_pool()
    row = await pool.fetchrow(
        f"UPDATE webhooks SET {', '.join(sets)} "
        f"WHERE workspace_id = ${idx} AND user_id = ${idx + 1} "
        "RETURNING id, workspace_id, user_id, url, secret, event_filter, is_active, created_at, updated_at",
        *args,
    )
    return _row_to_dict(row) if row else None


async def delete_webhook(workspace_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
        workspace_id, user_id,
    )
    return result == "DELETE 1"


async def get_webhooks_for_workspace(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, user_id, url, secret, event_filter "
        "FROM webhooks WHERE workspace_id = $1 AND is_active = true",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def deliver_webhook(webhook: dict, event: dict):
    payload = json.dumps(event, default=str)
    headers = {"Content-Type": "application/json"}
    if webhook.get("secret"):
        sig = hmac.new(
            webhook["secret"].encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Webhook-Signature"] = sig
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(webhook["url"], content=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "Webhook delivery failed for user %s: HTTP %d",
                    webhook["user_id"], resp.status_code,
                )
    except Exception:
        logger.warning(
            "Webhook delivery error for user %s", webhook["user_id"], exc_info=True,
        )


async def dispatch_webhooks(
    workspace_id: UUID, event_type: str, event: dict,
    sender_id: UUID | None = None,
):
    """Dispatch webhooks for a workspace event."""
    try:
        webhooks = await get_webhooks_for_workspace(workspace_id)
    except Exception:
        logger.warning("Failed to fetch webhooks for workspace %s", workspace_id, exc_info=True)
        return
    envelope = {
        "event": event_type,
        "workspace_id": str(workspace_id),
        "data": event,
    }
    for wh in webhooks:
        if sender_id and wh["user_id"] == sender_id:
            continue
        # Check event filter
        ef = wh.get("event_filter", [])
        if ef and event_type not in ef:
            continue
        asyncio.create_task(deliver_webhook(wh, envelope))


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["has_secret"] = d.pop("secret", None) is not None
    return d
