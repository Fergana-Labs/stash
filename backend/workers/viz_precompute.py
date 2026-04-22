"""Background precompute for dashboard visualizations.

The knowledge-density query stems the full accessible corpus — fast after
the LATERAL rewrite, but still not something we want blocking a page load.
This worker walks users active in the last 7 days and refreshes their
density cache every ~6 hours so the endpoint stays a pure read.

One worker per uvicorn process. A pg advisory lock gates each user so two
workers can't recompute the same user concurrently."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from ..database import get_pool
from ..services import analytics_service

logger = logging.getLogger(__name__)

TICK_SECONDS = 600.0
ERROR_SLEEP_SECONDS = 60.0
ACTIVE_WINDOW = timedelta(days=7)
REFRESH_AFTER = timedelta(hours=6)
BATCH_SIZE = 20


async def _recompute_one(user_id) -> None:
    clusters, signature = await analytics_service.compute_knowledge_density(user_id)
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO knowledge_density_cache (user_id, workspace_id, clusters, source_signature, computed_at)
        VALUES ($1, NULL, $2, $3, now())
        ON CONFLICT (user_id, workspace_id)
        DO UPDATE SET clusters = EXCLUDED.clusters,
                      source_signature = EXCLUDED.source_signature,
                      computed_at = EXCLUDED.computed_at
        """,
        user_id,
        clusters,
        signature,
    )


async def _tick() -> int:
    pool = get_pool()
    active_since = datetime.now(UTC) - ACTIVE_WINDOW
    refresh_cutoff = datetime.now(UTC) - REFRESH_AFTER

    rows = await pool.fetch(
        """
        SELECT u.id
        FROM users u
        LEFT JOIN knowledge_density_cache kdc
               ON kdc.user_id = u.id AND kdc.workspace_id IS NULL
        WHERE u.last_seen >= $1
          AND (kdc.computed_at IS NULL OR kdc.computed_at < $2)
        ORDER BY kdc.computed_at ASC NULLS FIRST
        LIMIT $3
        """,
        active_since,
        refresh_cutoff,
        BATCH_SIZE,
    )
    if not rows:
        return 0

    done = 0
    for r in rows:
        try:
            await _recompute_one(r["id"])
            done += 1
        except Exception:
            logger.exception("viz precompute failed for user %s", r["id"])
    return done


async def run() -> None:
    """Run until cancelled. Safe to start from FastAPI lifespan."""
    logger.info("viz precompute worker started")
    while True:
        try:
            count = await _tick()
            if count:
                logger.info("viz precompute: refreshed %d user(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("viz precompute tick failed")
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue
        await asyncio.sleep(TICK_SECONDS)
