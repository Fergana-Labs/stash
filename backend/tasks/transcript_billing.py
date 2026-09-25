"""Deliver the transactional usage outbox to Stripe without unbounded billing retries."""

import asyncio
from datetime import UTC, datetime, timedelta

import stripe

from ..celery_app import celery
from ..config import settings
from ..database import get_pool
from ..services.transcript_usage_service import METER_EVENT_NAME
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.transcript_billing.report_usage")
def report_usage() -> int:
    return run_async(_report_usage())


async def _report_usage() -> int:
    await get_pool().execute("DELETE FROM curation_batches WHERE expires_at < now()")
    if settings.STRIPE_SECRET_KEY is None:
        return 0
    sent = 0
    for _ in range(25):
        async with get_pool().acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM transcript_meter_events WHERE reported_at IS NULL "
                "AND (last_attempt_at IS NULL OR last_attempt_at < now()-interval '5 minutes') "
                "AND (first_attempt_at IS NULL OR first_attempt_at > now()-interval '23 hours') "
                "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
            )
            if row is None:
                break
            await conn.execute(
                "UPDATE transcript_meter_events SET first_attempt_at=coalesce(first_attempt_at,now()),last_attempt_at=now() WHERE id=$1",
                row["id"],
            )
        if row["created_at"] < datetime.now(UTC) - timedelta(days=34):
            raise RuntimeError(
                f"Usage event {row['id']} is too old to report; reconcile it manually."
            )
        try:
            await asyncio.to_thread(
                stripe.billing.MeterEvent.create,
                event_name=METER_EVENT_NAME,
                payload={"stripe_customer_id": row["customer_id"], "value": str(row["tokens"])},
                identifier=str(row["id"]),
                idempotency_key=str(row["id"]),
                timestamp=int(row["created_at"].timestamp()),
                api_key=settings.STRIPE_SECRET_KEY,
            )
        except stripe.StripeError as exc:
            await get_pool().execute(
                "UPDATE transcript_meter_events SET error=$2 WHERE id=$1", row["id"], str(exc)
            )
            raise
        await get_pool().execute(
            "UPDATE transcript_meter_events SET reported_at=now(),error=NULL WHERE id=$1", row["id"]
        )
        sent += 1
    # Stripe guarantees meter-event deduplication for only 24 hours. A lost
    # acknowledgement older than that needs reconciliation, never blind replay.
    stalled = await get_pool().fetchval(
        "SELECT count(*) FROM transcript_meter_events WHERE reported_at IS NULL "
        "AND first_attempt_at <= now()-interval '23 hours'"
    )
    if stalled:
        raise RuntimeError(f"{stalled} transcript usage events need manual Stripe reconciliation.")
    return sent
