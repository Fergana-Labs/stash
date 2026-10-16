"""Test run scoring: one judge call per case and scorer, so it runs on the heavy queue."""

from uuid import UUID

from ..celery_app import celery
from ..services.test_sets import service
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.test_sets.score_run", soft_time_limit=1700, time_limit=1800)
def score_run(run_id: str):
    run_async(service.score_run(UUID(run_id)))
