"""Standalone Agent Judge investigations: many model calls, so they run on the heavy queue."""

from uuid import UUID

from ..celery_app import celery
from ..services.agent_judge import grading
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.agent_judge.investigate", soft_time_limit=900, time_limit=960)
def investigate(report_id: str):
    run_async(grading.investigate(UUID(report_id)))
