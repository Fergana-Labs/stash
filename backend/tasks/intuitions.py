"""Eval (intuition model) background jobs; judge and Claude calls take minutes."""

from uuid import UUID

from ..celery_app import celery
from ..services.intuition import drop_folder, rubric_builder
from ..services.intuition import improve as improve_service
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.intuitions.improve", soft_time_limit=1700, time_limit=1800)
def improve(job_id: str):
    run_async(improve_service.run(UUID(job_id)))


@celery.task(name="backend.tasks.intuitions.refine", soft_time_limit=1700, time_limit=1800)
def refine(job_id: str):
    run_async(rubric_builder.run(UUID(job_id)))


@celery.task(name="backend.tasks.intuitions.drop_folders_due")
def drop_folders_due():
    """Beat tick: queue an import for each eval whose drop folder has something new."""
    ids = run_async(drop_folder.due())
    for model_id in ids:
        sync_drop_folder.delay(str(model_id))
    return {"models": len(ids)}


@celery.task(name="backend.tasks.intuitions.sync_drop_folder", soft_time_limit=540, time_limit=600)
def sync_drop_folder(model_id: str):
    return run_async(drop_folder.sync(UUID(model_id)))
