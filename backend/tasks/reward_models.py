"""Reward model training and GEPA skill creation tasks (dedicated reward queue)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ..services.rm import evaluator, jobs
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


async def score_trace_async(run_id: UUID) -> None:
    # Duplicate deliveries must not run inference twice or overwrite a completed job.
    claimed = await get_pool().fetchval(
        "UPDATE rm_scoring_runs SET status = 'running', started_at = now() WHERE id = $1 AND status = 'queued' RETURNING id",
        run_id,
    )
    if claimed is None:
        return
    await _run_tracked("rm_scoring_runs", run_id, jobs.run_scoring)


async def train_evaluator_async(model_id: UUID) -> None:
    claimed = await get_pool().fetchval(
        "UPDATE rm_reward_models SET status = 'running', started_at = now() WHERE id = $1 AND scope = 'shared' AND status = 'queued' RETURNING id",
        model_id,
    )
    if claimed is not None:
        await _run_tracked("rm_reward_models", model_id, evaluator.train_candidate)


@celery.task(
    name="backend.tasks.reward_models.train_evaluator", soft_time_limit=3800, time_limit=3900
)
def train_evaluator(model_id: str) -> None:
    run_async(train_evaluator_async(UUID(model_id)))


@celery.task(name="backend.tasks.reward_models.collect_examples")
def collect_examples(trace_id: str) -> None:
    run_async(evaluator.collect_examples(UUID(trace_id)))


@celery.task(name="backend.tasks.reward_models.reconcile")
def reconcile() -> None:
    run_async(evaluator.reconcile())


@celery.task(name="backend.tasks.reward_models.score_trace")
def score_trace(run_id: str) -> None:
    run_async(score_trace_async(UUID(run_id)))


@celery.task(name="backend.tasks.reward_models.train_reward_model")
def train_reward_model(model_id: str) -> None:
    run_async(train_reward_model_async(UUID(model_id)))


@celery.task(name="backend.tasks.reward_models.run_gepa")
def run_gepa(run_id: str) -> None:
    run_async(run_gepa_async(UUID(run_id)))
