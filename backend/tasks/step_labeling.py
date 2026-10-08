"""Automatic step labels for traces. See services/rm/step_labeling.py."""

from uuid import UUID

from ..celery_app import celery
from ..services.rm import step_labeling
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.step_labeling.reconcile")
def reconcile() -> int:
    """Beat dispatcher: claim traces that are due and hand each to the heavy queue."""
    trace_ids = run_async(step_labeling.claim_due())
    for trace_id in trace_ids:
        label_trace.delay(str(trace_id))
    return len(trace_ids)


@celery.task(name="backend.tasks.step_labeling.label_trace", soft_time_limit=1500, time_limit=1560)
def label_trace(trace_id: str) -> str:
    return run_async(step_labeling.label_trace(UUID(trace_id)))
