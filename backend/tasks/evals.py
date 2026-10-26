"""Judge eval background work: rubric builds on the heavy queue; the channel agent on the
default queue, where a reply never waits behind a minutes-long build; and a sweep every
minute that restarts what a lost task left stuck."""

from uuid import UUID

from ..celery_app import celery
from ..services.evals import build, channel, service
from ._celery_helpers import run_async

ERROR_CHARS = 500


async def build_eval_async(eval_id: UUID) -> None:
    claimed = await service.claim_build(eval_id)
    if claimed is None:
        return  # another worker took this build
    try:
        await build.run(eval_id, fresh=claimed["fresh"])
    except Exception as exc:
        await build._set(eval_id, stage="failed", error=str(exc)[-ERROR_CHARS:])
        raise
    finally:
        await service.finish_build(eval_id)


@celery.task(name="backend.tasks.evals.build_eval", soft_time_limit=1500, time_limit=1560)
def build_eval(eval_id: str) -> None:
    run_async(build_eval_async(UUID(eval_id)))


@celery.task(name="backend.tasks.evals.read_channel", soft_time_limit=240, time_limit=300)
def read_channel(eval_id: str) -> None:
    run_async(channel.run(UUID(eval_id)))


@celery.task(name="backend.tasks.evals.sweep", soft_time_limit=50, time_limit=60)
def sweep() -> dict:
    return run_async(service.sweep())
