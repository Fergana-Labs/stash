"""Image eval builds (style brief + imitations + training) on the reward queue."""

from __future__ import annotations

from uuid import UUID

from ..celery_app import celery
from ..services.image_eval import build
from ._celery_helpers import run_async

ERROR_CHARS = 2000


async def build_classifier_async(classifier_id: UUID) -> None:
    try:
        await build.run(classifier_id)
    except Exception as exc:
        await build._set(classifier_id, stage="failed", error=str(exc)[-ERROR_CHARS:])
        raise


@celery.task(name="backend.tasks.image_evals.build_classifier")
def build_classifier(classifier_id: str) -> None:
    run_async(build_classifier_async(UUID(classifier_id)))
