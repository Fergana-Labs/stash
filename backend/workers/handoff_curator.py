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
from ._lock_helpers import advisory_lock
from ..services import ask_service, handoff_curator

logger = logging.getLogger(__name__)

TICK_SECONDS = 60.0
ERROR_SLEEP_SECONDS = 60.0
QUIET_PERIOD = timedelta(minutes=5)
MIN_GAP_BETWEEN_REGENS = timedelta(hours=24)
ERROR_BACKOFF_BASE = timedelta(minutes=10)
BATCH_SIZE = 5
LOCK_NAMESPACE = 0x484E4446  # 'HNDF'
PER_REGEN_TIMEOUT = 300.0


def _make_executor(workspace_id):
    """Bind ask_service._execute_tool to this stash so the curator's tool
    catalog matches what ask would see for the same stash."""

    async def _exec(name: str, args: dict):
        return await ask_service._execute_tool(name, args, workspace_id)

    return _exec


async def _regenerate_one(workspace_id) -> None:
    executor = _make_executor(workspace_id)
    await asyncio.wait_for(
        handoff_curator.regenerate(workspace_id, executor),
        timeout=PER_REGEN_TIMEOUT,
    )


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
        async with advisory_lock(LOCK_NAMESPACE, str(r["workspace_id"])) as conn:
            if conn is None:
                continue
            try:
                await _regenerate_one(r["workspace_id"])
                done += 1
            except asyncio.TimeoutError:
                logger.warning(
                    "handoff curator: regen timed out for %s",
                    r["workspace_id"],
                )
                await handoff_curator._record_failure(
                    r["workspace_id"], "regen wall-clock timeout"
                )
            except Exception:
                logger.exception(
                    "handoff curator: unexpected error for %s",
                    r["workspace_id"],
                )
    return done


async def force_regenerate(workspace_id) -> None:
    """User-triggered regen path. Bypasses the 24h gap; still respects the
    advisory lock so simultaneous clicks don't fan out into two LLM calls.

    Used by the API's `?wait=true` flow.
    """
    async with advisory_lock(LOCK_NAMESPACE, str(workspace_id)) as conn:
        if conn is None:
            return
        await _regenerate_one(workspace_id)


async def run() -> None:
    logger.info("handoff curator worker started")
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("handoff curator tick failed")
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue
        await asyncio.sleep(TICK_SECONDS)
