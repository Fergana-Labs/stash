"""Transcript text is metered once, after successful curation, in UTC calendar months."""

from datetime import UTC, datetime
from functools import lru_cache
from uuid import UUID

import tiktoken
from fastapi import HTTPException

from ..database import get_pool
from . import billing_service

FREE_TOKENS = 100_000
PRO_TOKENS = 2_000_000
OVERAGE_CENTS_PER_MILLION = 1_000
METER_EVENT_NAME = "transcript_overage_tokens"


@lru_cache(maxsize=1)
def _encoding():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(content: str) -> int:
    # Transcript text may literally contain tokenizer control strings.
    return len(_encoding().encode(content, disallowed_special=()))


async def allowance(owner: UUID, now: datetime, *, conn=None) -> dict:
    db = get_pool() if conn is None else conn
    start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    account = await db.fetchrow(
        "SELECT u.plan,u.email,s.status,s.overage_limit_cents,s.usage_item_id,s.stripe_customer_id "
        "FROM users u LEFT JOIN user_subscriptions s ON s.user_id=u.id WHERE u.id=$1",
        owner,
    )
    if account is None:
        raise ValueError("Usage account does not exist")
    plan = billing_service.plan_from_account(account)
    used = await db.fetchval(
        "SELECT coalesce(sum(tokens),0)::bigint FROM transcript_usage "
        "WHERE owner_user_id=$1 AND processed_at >= $2 AND processed_at < $3",
        owner,
        start,
        end,
    )
    overage = await db.fetchval(
        "SELECT coalesce(sum(tokens),0)::bigint FROM transcript_meter_events "
        "WHERE owner_user_id=$1 AND created_at >= $2 AND created_at < $3",
        owner,
        start,
        end,
    )
    included = None if plan == "enterprise" else PRO_TOKENS if plan == "pro" else FREE_TOKENS
    cap = 0 if account["overage_limit_cents"] is None else account["overage_limit_cents"]
    enabled = (
        billing_service.billing_enabled()
        and plan == "pro"
        and account["status"] == "active"
        and account["usage_item_id"] is not None
        and cap > 0
    )
    extra = max(0, cap * 1_000_000 // OVERAGE_CENTS_PER_MILLION - overage) if enabled else 0
    remaining = None if included is None else max(0, included - used) + extra
    return {
        "plan": plan,
        "used": used,
        "included": included,
        "limit": None if remaining is None else used + remaining,
        "remaining": remaining,
        "period": "month",
        "resets_at": end.isoformat(),
        "overage_tokens": overage,
        "overage_limit_cents": cap,
        "overage_cents": overage * OVERAGE_CENTS_PER_MILLION / 1_000_000,
        "overages_enabled": enabled,
        "customer_id": account["stripe_customer_id"],
    }


async def record(conn, owner: UUID, events: list[dict], now: datetime) -> None:
    """Called inside the same transaction as curation progress; serialize account spending."""
    await conn.fetchval("SELECT id FROM users WHERE id=$1 FOR UPDATE", owner)
    budget = await allowance(owner, now, conn=conn)
    added = 0
    for event in events:
        tokens = await conn.fetchval(
            "INSERT INTO transcript_usage(owner_user_id,content_key,tokens,processed_at) "
            "VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING tokens",
            owner,
            event["content_key"],
            0 if event["session_id"] is None else count_tokens(event["content"]),
            now,
        )
        if tokens is not None:
            added += tokens
    if budget["remaining"] is not None and added > budget["remaining"]:
        raise HTTPException(
            402,
            "Transcript token allowance changed during curation. Retry after increasing your limit.",
        )
    if budget["included"] is None:
        return
    overage = max(0, added - max(0, budget["included"] - budget["used"]))
    if overage:
        await conn.execute(
            "INSERT INTO transcript_meter_events(owner_user_id,customer_id,tokens,created_at) VALUES ($1,$2,$3,$4)",
            owner,
            budget["customer_id"],
            overage,
            now,
        )
