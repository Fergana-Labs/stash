"""Judge eval builds (traits plus an agreement check) on the heavy queue."""

from uuid import UUID

from ..celery_app import celery
from ..services.evals import build
from ._celery_helpers import run_async

ERROR_CHARS = 500


async def build_eval_async(eval_id: UUID) -> None:
    try:
        await build.run(eval_id)
    except Exception as exc:
        await build._set(eval_id, stage="failed", error=str(exc)[-ERROR_CHARS:])
        raise


@celery.task(name="backend.tasks.evals.build_eval", soft_time_limit=1500, time_limit=1560)
def build_eval(eval_id: str) -> None:
    run_async(build_eval_async(UUID(eval_id)))
