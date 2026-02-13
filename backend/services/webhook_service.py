import asyncio
import hashlib
import hmac
import json
import logging
from uuid import UUID

import httpx

from ..database import get_pool

logger = logging.getLogger("moltchat")


async def create_webhook(user_id: UUID, url: str, secret: str | None = None) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO webhooks (user_id, url, secret)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id) DO UPDATE
             SET url = EXCLUDED.url,
                 secret = EXCLUDED.secret,
                 is_active = true,
                 updated_at = now()
           RETURNING id, user_id, url, secret, is_active, created_at, updated_at""",
        user_id,
        url,
        secret,
    )
    return _row_to_dict(row)


async def get_webhook(user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, user_id, url, secret, is_active, created_at, updated_at "
        "FROM webhooks WHERE user_id = $1",
        user_id,
    )
    if not row:
        return None
    return _row_to_dict(row)


async def update_webhook(
    user_id: UUID,
    url: str | None = None,
    secret: str | None = None,
    is_active: bool | None = None,
) -> dict | None:
    sets: list[str] = []
    args: list = []
    idx = 1

    if url is not None:
        sets.append(f"url = ${idx}")
        args.append(url)
        idx += 1
    if secret is not None:
        sets.append(f"secret = ${idx}")
        args.append(secret)
        idx += 1
    if is_active is not None:
        sets.append(f"is_active = ${idx}")
        args.append(is_active)
        idx += 1

    if not sets:
        return await get_webhook(user_id)

    sets.append("updated_at = now()")
    args.append(user_id)

    query = (
        f"UPDATE webhooks SET {', '.join(sets)} "
        f"WHERE user_id = ${idx} "
        f"RETURNING id, user_id, url, secret, is_active, created_at, updated_at"
    )
    pool = get_pool()
    row = await pool.fetchrow(query, *args)
    if not row:
        return None
    return _row_to_dict(row)


async def delete_webhook(user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute("DELETE FROM webhooks WHERE user_id = $1", user_id)
    return result == "DELETE 1"


async def get_webhooks_for_room(room_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT w.id, w.user_id, w.url, w.secret
           FROM webhooks w
           JOIN room_members rm ON rm.user_id = w.user_id
           WHERE rm.room_id = $1 AND w.is_active = true""",
        room_id,
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
                    webhook["user_id"],
                    resp.status_code,
                )
    except Exception:
        logger.warning(
            "Webhook delivery error for user %s", webhook["user_id"], exc_info=True
        )


async def dispatch_webhooks(room_id: UUID, event: dict, sender_id: UUID | None = None):
    try:
        webhooks = await get_webhooks_for_room(room_id)
    except Exception:
        logger.warning("Failed to fetch webhooks for room %s", room_id, exc_info=True)
        return
    envelope = {"event": event.get("type", "unknown"), "room_id": str(room_id), "data": event}
    for wh in webhooks:
        # Don't send webhook to the user who triggered the event
        if sender_id and wh["user_id"] == sender_id:
            continue
        asyncio.create_task(deliver_webhook(wh, envelope))


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["has_secret"] = d.pop("secret", None) is not None
    return d
