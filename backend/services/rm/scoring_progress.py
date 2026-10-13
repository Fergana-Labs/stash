"""Best-effort progress for a Run, separate from model training progress."""

import logging
from datetime import UTC, datetime

from ...database import get_pool

logger = logging.getLogger(__name__)


async def save_customer(run_id, event):
    await save(run_id, event, customer=True)


async def save(run_id, event, *, customer=False):
    table = "rm_customer_scoring_runs" if customer else "rm_scoring_runs"
    try:
        await get_pool().execute(
            f"UPDATE {table} SET progress=$2::jsonb WHERE id=$1 AND status='running'",
            run_id,
            event,
        )
    except Exception:
        logger.warning("Could not save scoring progress for %s", run_id, exc_info=True)


async def stage(run_id, name, *, customer=False):
    await save(
        run_id,
        {
            "stage": name,
            "completed": 0,
            "total": 0,
            "elapsed_seconds": 0,
            "updated_at": datetime.now(UTC).isoformat(),
        },
        customer=customer,
    )
