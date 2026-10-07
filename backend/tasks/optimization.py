"""Online optimization jobs; checkpoint inference runs on Modal."""

from uuid import UUID

from ..celery_app import celery
from ..services.rm import optimization_worker
from ._celery_helpers import run_async


@celery.task(name="backend.tasks.optimization.reconcile")
def reconcile():
    run_async(optimization_worker.reconcile())


@celery.task(
    name="backend.tasks.optimization.generate_candidate", soft_time_limit=200, time_limit=240
)
def generate_candidate(round_id: str):
    run_async(optimization_worker.generate(UUID(round_id)))


@celery.task(name="backend.tasks.optimization.score_run", soft_time_limit=1450, time_limit=1500)
def score_run(run_id: str):
    run_async(optimization_worker.score(UUID(run_id)))
