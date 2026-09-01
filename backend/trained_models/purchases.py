"""Training purchases: one row per paid training run.

Kept apart from the rest of the service because the Stripe webhook needs to
record a purchase without importing anything that imports billing — this
module touches only the database.
"""

from __future__ import annotations

from uuid import UUID

from ..database import get_pool


async def record(owner_user_id: UUID, kind: str, stripe_session_id: str, amount_cents: int) -> bool:
    """Record a completed checkout. Stripe delivers webhooks at least once, so
    a session id already on file is not an error; it is the same purchase.
    Returns True when a new row was written."""
    row = await get_pool().fetchrow(
        """
        INSERT INTO training_purchases (owner_user_id, kind, stripe_session_id, amount_cents)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (stripe_session_id) DO NOTHING
        RETURNING id
        """,
        owner_user_id,
        kind,
        stripe_session_id,
        amount_cents,
    )
    return row is not None


async def spendable(owner_user_id: UUID, kind: str) -> UUID | None:
    """The oldest unconsumed purchase for this kind, if any."""
    return await get_pool().fetchval(
        "SELECT id FROM training_purchases "
        "WHERE owner_user_id = $1 AND kind = $2 AND consumed_by IS NULL "
        "ORDER BY created_at LIMIT 1",
        owner_user_id,
        kind,
    )


async def spendable_count(owner_user_id: UUID, kind: str) -> int:
    return await get_pool().fetchval(
        "SELECT count(*) FROM training_purchases "
        "WHERE owner_user_id = $1 AND kind = $2 AND consumed_by IS NULL",
        owner_user_id,
        kind,
    )


async def restore(model_id: UUID) -> None:
    """A training run that failed did not deliver what was paid for; the
    purchase becomes spendable again."""
    await get_pool().execute(
        "UPDATE training_purchases SET consumed_by = NULL WHERE consumed_by = $1", model_id
    )
