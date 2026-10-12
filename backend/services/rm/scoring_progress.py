"""Best-effort progress for a Run, separate from model training progress."""

import logging
from datetime import UTC, datetime

from ...database import get_pool

logger = logging.getLogger(__name__)


async def save(run_id, event):
    try:
        await get_pool().execute(
            "UPDATE rm_scoring_runs SET progress=$2::jsonb WHERE id=$1 AND status='running'",
            run_id,
            event,
        )
    except Exception:
        logger.warning("Could not save scoring progress for %s", run_id, exc_info=True)


async def stage(run_id, name):
    await save(
        run_id,
        {
            "stage": name,
            "completed": 0,
            "total": 0,
            "elapsed_seconds": 0,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
