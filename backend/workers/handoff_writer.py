"""Background worker that regenerates stash handoff docs.

Cadence: daily per stash. The stale flag accumulates dirty signals between
runs; the next daily tick consumes them all in one regen.

A per-stash advisory lock prevents N uvicorn workers from double-rendering
the same stash on the same tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from ..database import get_pool
from ..services import handoff_writer
from ._lock_helpers import advisory_lock

logger = logging.getLogger(__name__)

TICK_SECONDS = 60.0
ERROR_SLEEP_SECONDS = 60.0
QUIET_PERIOD = timedelta(minutes=5)
MIN_GAP_BETWEEN_REGENS = timedelta(hours=24)
ERROR_BACKOFF_BASE = timedelta(minutes=10)
BATCH_SIZE = 5
LOCK_NAMESPACE = 0x484E4446  # 'HNDF'


async def _regenerate_one(workspace_id) -> None:
    await asyncio.wait_for(
        handoff_writer.regenerate(workspace_id),
        timeout=handoff_writer.PER_REGEN_TIMEOUT,
    )


async def regenerate_under_lock(workspace_id) -> bool:
    """Run regenerate() inside the advisory lock. Returns False if another
    worker holds the lock (we skip rather than queue). Used by the
    synchronous /handoff/regenerate route too."""
    async with advisory_lock(LOCK_NAMESPACE, str(workspace_id)) as conn:
        if conn is None:
            return False
        await _regenerate_one(workspace_id)
        return True


async def wait_for_completion(workspace_id, timeout: float) -> bool:
    """Poll until the row is fresh (stale=FALSE, generated_at IS NOT NULL).
    Used by the synchronous /handoff/regenerate endpoint when another
    process holds the lock: we wait for them to finish rather than
    double-spending tokens."""
    pool = get_pool()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        row = await pool.fetchrow(
            "SELECT stale, generated_at FROM stash_handoffs WHERE workspace_id = $1",
            workspace_id,
        )
        if row and not row["stale"] and row["generated_at"] is not None:
            return True
        await asyncio.sleep(1.0)
    return False


async def _tick() -> int:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT workspace_id FROM stash_handoffs
        WHERE stale = TRUE
          AND pinned_at IS NULL
          AND stale_marked_at <= now() - $1::interval
          AND (generated_at IS NULL OR generated_at <= now() - $2::interval)
          AND (
                last_attempt_at IS NULL
                OR last_attempt_at <= now() - ($3::interval * power(2, LEAST(consecutive_failures, 6)))
          )
        ORDER BY stale_marked_at ASC
        LIMIT $4
        """,
        QUIET_PERIOD,
        MIN_GAP_BETWEEN_REGENS,
        ERROR_BACKOFF_BASE,
        BATCH_SIZE,
    )
    if not rows:
        return 0

    done = 0
    for r in rows:
        try:
            ran = await regenerate_under_lock(r["workspace_id"])
            if ran:
                done += 1
        except TimeoutError:
            logger.warning("handoff writer: regen timed out for %s", r["workspace_id"])
            await handoff_writer._record_failure(r["workspace_id"], "regen wall-clock timeout")
        except Exception:
            logger.exception("handoff writer: unexpected error for %s", r["workspace_id"])
    return done


async def run() -> None:
    logger.info("handoff writer worker started")
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("handoff writer tick failed")
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue
        await asyncio.sleep(TICK_SECONDS)
