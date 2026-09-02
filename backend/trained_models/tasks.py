"""Following a training run to its end.

The GPU job was spawned by the request that queued the model, so all the
worker does is ask after it. Each poll is its own short task that re-queues
itself: nothing holds a worker slot for the minutes a run takes, and a
worker that dies mid-poll is simply redelivered to.
"""

from __future__ import annotations

from uuid import UUID

from ..celery_app import celery
from ..tasks._celery_helpers import run_async
from . import service

POLL_EVERY_S = 30


@celery.task(name="backend.trained_models.tasks.poll_training")
def poll_training(model_id: str) -> str:
    status = run_async(service.advance_training(UUID(model_id)))
    if status == "training":
        poll_training.apply_async(args=[model_id], countdown=POLL_EVERY_S)
    return status
