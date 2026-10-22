"""Durable taste workflow tasks. Model execution is remote only."""

from uuid import UUID

from ..celery_app import celery
from ..services import taste
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.taste.run", soft_time_limit=2700, time_limit=2800)
def run(job_id: str):
    run_async(taste.run_job(UUID(job_id)))
