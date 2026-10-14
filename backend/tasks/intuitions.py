"""Eval (intuition model) background jobs; judge and Claude calls take minutes."""

from uuid import UUID

from ..celery_app import celery
from ..services.intuition import improve as improve_service
from ..services.intuition import rubric_builder
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.intuitions.improve", soft_time_limit=1700, time_limit=1800)
def improve(job_id: str):
    run_async(improve_service.run(UUID(job_id)))


@celery.task(name="backend.tasks.intuitions.refine", soft_time_limit=1700, time_limit=1800)
def refine(job_id: str):
    run_async(rubric_builder.run(UUID(job_id)))
