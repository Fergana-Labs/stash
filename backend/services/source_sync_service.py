"""One queued or running sync per source, shared by every trigger."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from ..celery_app import celery
from ..database import get_pool

# Longer than Celery's 30-minute hard limit. Dead workers and failed publishes
# can be reclaimed, without mistaking a healthy long crawl for a dead worker.
SYNC_LEASE_MINUTES = 35


async def enqueue_sync(source_id: UUID) -> str | None:
    task_id = str(uuid4())
    claimed = await get_pool().fetchval(
        f"""
        UPDATE user_sources SET
            sync_task_id = $2, sync_claimed_at = now(), sync_started_at = NULL,
            sync_status = 'syncing', sync_error = NULL,
            next_sync_at = now() + sync_interval_s * interval '1 second',
            updated_at = now()
        WHERE id = $1 AND sync_enabled
          AND (sync_task_id IS NULL
               OR sync_claimed_at < now() - interval '{SYNC_LEASE_MINUTES} minutes')
        RETURNING id
        """,
        source_id,
        task_id,
    )
    if claimed is None:
        return None
    try:
        await asyncio.to_thread(
            celery.send_task,
            "backend.tasks.sources.sync_source",
            kwargs={"source_id": str(source_id)},
            task_id=task_id,
        )
    except Exception:
        # Publishing can fail during a broker outage. Release only this claim
        # and preserve the error, so the next tick can retry it.
        await get_pool().execute(
            "UPDATE user_sources SET sync_task_id = NULL, sync_claimed_at = NULL, "
            "sync_status = 'failed', sync_error = 'Could not queue sync.', "
            "next_sync_at = now() WHERE id = $1 AND sync_task_id = $2",
            source_id,
            task_id,
        )
        raise
    return task_id


async def start_sync(source_id: UUID, task_id: str) -> bool:
    return (
        await get_pool().fetchval(
            "UPDATE user_sources SET sync_started_at = now(), sync_claimed_at = now() "
            "WHERE id = $1 AND sync_task_id = $2 AND sync_started_at IS NULL "
            "AND sync_enabled RETURNING id",
            source_id,
            task_id,
        )
        is not None
    )


async def finish_sync(source_id: UUID, task_id: str) -> None:
    await get_pool().execute(
        "UPDATE user_sources SET sync_task_id = NULL, sync_claimed_at = NULL, "
        "sync_started_at = NULL WHERE id = $1 AND sync_task_id = $2",
        source_id,
        task_id,
    )
