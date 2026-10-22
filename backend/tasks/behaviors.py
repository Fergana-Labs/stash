"""Behavior detection: a cheap beat tick (segments, rules, alerts) that hands
model-detected behaviors to the heavy queue when any are due."""

from uuid import UUID

from ..celery_app import celery
from ..services.behaviors import scan
from ..services.behaviors import triage as triage_service
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.behaviors.reconcile")
def reconcile():
    result = run_async(scan.reconcile())
    if result.get("models_due"):
        scan_models.delay()
    return result


@celery.task(name="backend.tasks.behaviors.scan_models", soft_time_limit=900, time_limit=960)
def scan_models():
    return run_async(scan.scan_models())


@celery.task(name="backend.tasks.behaviors.triage", soft_time_limit=600, time_limit=660)
def triage(triage_id: str):
    run_async(triage_service.run(UUID(triage_id)))
