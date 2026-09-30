"""Reward model training and GEPA skill creation tasks (dedicated reward queue)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ..services.rm import jobs
from ._celery_helpers import run_async

ERROR_CHARS = 2000


async def _run_tracked(table: str, job_id: UUID, run: Callable[[UUID], Awaitable[None]]) -> None:
    """Mark a job row running, then failed if `run` raises.

    `run` itself marks the row succeeded, in the same transaction that stores
    its results.
    """
    pool = get_pool()
    await pool.execute(
        f"UPDATE {table} SET status = 'running', started_at = now() WHERE id = $1", job_id
    )
    try:
        await run(job_id)
    except Exception as exc:
        # WorkerFailed already carries the worker.log tail as its message.
        await pool.execute(
            f"UPDATE {table} SET status = 'failed', error = $2, finished_at = now() WHERE id = $1",
            job_id,
            str(exc)[-ERROR_CHARS:],
        )
        raise


async def train_reward_model_async(model_id: UUID) -> None:
    await _run_tracked("rm_reward_models", model_id, jobs.run_training)


async def run_gepa_async(run_id: UUID) -> None:
    await _run_tracked("rm_gepa_runs", run_id, jobs.run_gepa)


@celery.task(name="backend.tasks.reward_models.train_reward_model")
def train_reward_model(model_id: str) -> None:
    run_async(train_reward_model_async(UUID(model_id)))


@celery.task(name="backend.tasks.reward_models.run_gepa")
def run_gepa(run_id: str) -> None:
    run_async(run_gepa_async(UUID(run_id)))
