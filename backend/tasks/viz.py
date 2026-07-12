"""Viz precompute task.

Replaces `workers/viz_precompute.py`. Beat-scheduled (every 300s in
`celery_app.py`).

Walks users active in the last 7 days whose knowledge_density_cache is
older than 6 hours and recomputes their clusters.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ..services import analytics_service
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

ACTIVE_WINDOW = timedelta(days=7)
REFRESH_AFTER = timedelta(hours=6)
BATCH_SIZE = 20


async def _recompute_one(user_id) -> None:
    clusters, signature = await analytics_service.compute_knowledge_density(user_id)
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO knowledge_density_cache (user_id, owner_user_id, clusters, source_signature, computed_at)
        VALUES ($1, NULL, $2, $3, now())
        ON CONFLICT (user_id, owner_user_id)
        DO UPDATE SET clusters = EXCLUDED.clusters,
                      source_signature = EXCLUDED.source_signature,
                      computed_at = EXCLUDED.computed_at
        """,
        user_id,
        clusters,
        signature,
    )


async def _precompute() -> int:
    pool = get_pool()
    active_since = datetime.now(UTC) - ACTIVE_WINDOW
    refresh_cutoff = datetime.now(UTC) - REFRESH_AFTER

    rows = await pool.fetch(
        """
        SELECT u.id
        FROM users u
        LEFT JOIN knowledge_density_cache kdc
               ON kdc.user_id = u.id AND kdc.owner_user_id IS NULL
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
        except Exception as exc:
            logger.error(
                "viz precompute failed user=%s exception_type=%s",
                r["id"],
                type(exc).__name__,
            )
    if done:
        logger.info("viz precompute: refreshed %d user(s)", done)
    return done


@celery.task(name="backend.tasks.viz.precompute")
def precompute() -> int:
    return run_async(_precompute())


@celery.task(name="backend.tasks.viz.refresh_projection")
def refresh_projection(
    user_id: str, source: str | None = None, owner_user_id: str | None = None
) -> int:
    """Recompute one embedding projection, enqueued by the projection
    endpoint on cache miss or staleness. UMAP + numba live here because the
    web instances can't afford them (memory + latency)."""
    return run_async(
        analytics_service.compute_embedding_projection(
            UUID(user_id),
            source=source,
            owner_user_id=UUID(owner_user_id) if owner_user_id else None,
        )
    )
