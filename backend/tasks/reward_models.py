"""Reward model training and GEPA skill creation tasks (dedicated reward queue)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ..services.rm import evaluator, jobs, playground
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
    pool = get_pool()
    # An old broker delivery must not restart a completed/failed model or
    # submit the same active job again after a worker redeploy.
    model = await pool.fetchrow(
        """UPDATE rm_reward_models SET status='running', started_at=now(), error=NULL,
        finished_at=NULL, progress=NULL WHERE id=$1 AND status='queued' AND scope='personal'
        RETURNING compute""",
        model_id,
    )
    if model is None:
        return
    if model["compute"] != "modal":
        await _run_tracked("rm_reward_models", model_id, jobs.run_training)
        return
    from rm_worker import cloud_training

    try:
        await jobs.training_progress.stage(model_id, "starting")
        call_id = await asyncio.to_thread(cloud_training.dispatch, str(model_id))
    except Exception as exc:
        await pool.execute(
            """UPDATE rm_reward_models SET status='failed', error=$2, finished_at=now()
            WHERE id=$1 AND status='running'""",
            model_id,
            str(exc)[-ERROR_CHARS:],
        )
        raise
    # Keep this separate from dispatch errors: once submitted, the cloud job
    # owns completion. A failed metadata write must not mark its run failed.
    await pool.execute(
        """UPDATE rm_reward_models SET progress=coalesce(progress, '{}'::jsonb) || $2::jsonb
        WHERE id=$1 AND status='running'""",
        model_id,
        {"remote_call_id": call_id},
    )


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
    async def sweep():
        from ..services.rm import feature_jobs

        await evaluator.reconcile()
        await feature_jobs.reconcile()

    run_async(sweep())


@celery.task(
    name="backend.tasks.reward_models.compute_customer_features",
    soft_time_limit=1700,
    time_limit=1800,
)
def compute_customer_features(job_id: str) -> None:
    from ..services.rm.feature_jobs import run

    run_async(run(UUID(job_id)))


@celery.task(name="backend.tasks.reward_models.score_trace")
def score_trace(run_id: str) -> None:
    run_async(score_trace_async(UUID(run_id)))


@celery.task(name="backend.tasks.reward_models.train_reward_model")
def train_reward_model(model_id: str) -> None:
    run_async(train_reward_model_async(UUID(model_id)))


@celery.task(name="backend.tasks.reward_models.run_gepa")
def run_gepa(run_id: str) -> None:
    run_async(run_gepa_async(UUID(run_id)))


async def playground_async(run_id: UUID) -> None:
    claimed = await get_pool().fetchval(
        "UPDATE rm_playground_runs SET status = 'running', started_at = now() WHERE id = $1 AND status = 'queued' RETURNING id",
        run_id,
    )
    if claimed is not None:
        await _run_tracked("rm_playground_runs", run_id, playground.run_prediction)


@celery.task(name="backend.tasks.reward_models.playground_score")
def playground_score(run_id: str) -> None:
    run_async(playground_async(UUID(run_id)))
