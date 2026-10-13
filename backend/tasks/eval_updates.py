"""Cheap eval calibration on cached features; remote judging for new examples only."""

from uuid import UUID

from ..celery_app import celery
from ..database import get_pool
from ..services.intuition import updates
from ._celery_helpers import run_async


async def reconcile_async():
    rows = await get_pool().fetch("""WITH due AS (
        SELECT model_id FROM intuition_updates WHERE run_after<=now()
        AND (state='pending' OR (state IN ('queued','running')
        AND started_at<now()-interval '15 minutes'))
        ORDER BY run_after FOR UPDATE SKIP LOCKED LIMIT 50)
        UPDATE intuition_updates u SET state='queued',started_at=now()
        FROM due WHERE u.model_id=due.model_id RETURNING u.model_id""")
    failure = None
    for row in rows:
        try:
            update_eval.delay(str(row["model_id"]))
        except Exception as exc:
            await get_pool().execute(
                "UPDATE intuition_updates SET state='pending',started_at=NULL WHERE model_id=$1 AND state='queued'",
                row["model_id"],
            )
            failure = exc
    if failure is not None:
        raise failure


@celery.task(name="backend.tasks.eval_updates.reconcile")
def reconcile():
    run_async(reconcile_async())


@celery.task(name="backend.tasks.eval_updates.update_eval", soft_time_limit=600, time_limit=660)
def update_eval(model_id: str):
    run_async(updates.run(UUID(model_id)))
