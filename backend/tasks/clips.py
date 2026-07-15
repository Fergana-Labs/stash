"""URL-import worker: fetch URL-only clips out-of-band.

Work arrives in batches of ids rather than one task per URL so a 10k
bookmark import becomes ~100 queue entries — other periodic work
interleaves between batches instead of starving behind a flooded queue.
Rows are claimed with an attempts guard (see url_import_service), so
creation-time dispatch and the Beat sweep can overlap safely.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ..services import clip_router, url_import_service
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
CONCURRENCY = 8


async def _process_one(import_id: UUID) -> None:
    row = await url_import_service.claim(import_id)
    if row is None:
        return
    try:
        result = await clip_router.process_url_import(row)
    except Exception as exc:
        logger.warning(
            "url import failed id=%s exception_type=%s",
            import_id,
            type(exc).__name__,
        )
        await url_import_service.mark_failed(import_id, f"{type(exc).__name__}: {exc}")
        return
    await url_import_service.mark_done(
        import_id,
        page_id=result.get("page_id"),
        file_id=result.get("file_id"),
    )


async def _process_batch(ids: list[UUID]) -> str:
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def bounded(import_id: UUID) -> None:
        async with semaphore:
            await _process_one(import_id)

    await asyncio.gather(*(bounded(i) for i in ids))
    return f"processed {len(ids)}"


@celery.task(name="backend.tasks.clips.process_url_imports")
def process_url_imports(ids: list[str]) -> str:
    return run_async(_process_batch([UUID(i) for i in ids]))


def dispatch_url_imports(ids: list[UUID]) -> None:
    """Fan a set of import rows out to the worker in batch-sized tasks."""
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start : start + BATCH_SIZE]
        process_url_imports.delay([str(i) for i in chunk])


async def _enqueue_pending() -> int:
    """Sweep for rows that lost their dispatch (Redis blip, worker death).

    The age filter keeps the sweep from re-queueing rows whose
    creation-time dispatch is simply still in the queue.
    """
    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT id FROM url_imports
        WHERE (
                (status = 'pending' AND created_at < now() - INTERVAL '2 minutes')
             OR (status = 'failed' AND attempts < {url_import_service.MAX_ATTEMPTS})
             OR (status = 'processing' AND locked_at < now() - INTERVAL '10 minutes')
        )
        ORDER BY created_at
        LIMIT 1000
        """,
    )
    dispatch_url_imports([r["id"] for r in rows])
    return len(rows)


@celery.task(name="backend.tasks.clips.enqueue_pending_url_imports")
def enqueue_pending_url_imports() -> int:
    return run_async(_enqueue_pending())
