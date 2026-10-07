"""Bounded API grading and correction jobs; no local model training."""

from uuid import UUID

from ..celery_app import celery
from ..services.rm import workbench
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.workbench.reconcile")
def reconcile():
    return run_async(workbench.reconcile())


@celery.task(name="backend.tasks.workbench.assess_trace", soft_time_limit=900, time_limit=960)
def assess_trace(trace_id: str):
    return run_async(workbench.process_trace(UUID(trace_id)))


@celery.task(name="backend.tasks.workbench.prepare_feedback", soft_time_limit=180, time_limit=210)
def prepare_feedback(feedback_id: str):
    return run_async(workbench.prepare_feedback(UUID(feedback_id)))


@celery.task(name="backend.tasks.workbench.check_change", soft_time_limit=900, time_limit=960)
def check_change(change_id: str):
    return run_async(workbench.check_change(UUID(change_id)))
