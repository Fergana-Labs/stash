"""Detached GPU batches: load one checkpoint, publish each trace separately."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

import modal

from rm_worker.cloud_training import training_image
from rm_worker.modal_runner import SECRET_KEYS
from rm_worker.progress import Reporter

TIMEOUT_SECONDS = 20 * 60


async def score(batch_id: str) -> None:
    from backend import database
    from backend.services.rm import jobs, precompute, scoring_progress
    from rm_worker import score_run
    from rm_worker.artifacts import download_model
    from rm_worker.scoring import RewardModel

    bid = UUID(batch_id)
    await database.init_pool()
    pool = database.get_pool()
    previous = os.environ.get("RM_ARTIFACT_DIR")
    try:
        model = await pool.fetchrow(
            """SELECT m.id,m.owner_user_id,m.artifact_key,m.finished_at FROM rm_scoring_batches b
            JOIN rm_reward_models m ON m.id=b.reward_model_id AND m.owner_user_id=b.owner_user_id
            WHERE b.id=$1 AND b.status='running' AND m.scope='personal'
            AND m.compute='modal' AND m.status='succeeded' AND m.artifact_key IS NOT NULL""",
            bid,
        )
        if model is None:
            await precompute.fail(bid, "Reward model is unavailable for background scoring")
            return
        runs = await pool.fetch(
            """SELECT r.id,r.model_finished_at FROM rm_scoring_runs r JOIN rm_traces t ON t.id=r.trace_id
            WHERE r.batch_id=$1 AND r.owner_user_id=$2 AND t.owner_user_id=$2
            AND r.reward_model_id=$3 AND r.status='queued' ORDER BY r.created_at,r.id""",
            bid,
            model["owner_user_id"],
            model["id"],
        )
        if len(runs) > precompute.TRACES_PER_BATCH:
            raise ValueError("Background scoring batch exceeds its trace limit")
        if any(run["model_finished_at"] != model["finished_at"] for run in runs):
            raise ValueError("Reward model checkpoint changed before background scoring")
        if not runs:
            await pool.execute(
                """UPDATE rm_scoring_batches SET status='succeeded',finished_at=now()
                WHERE id=$1 AND status='running' AND NOT EXISTS
                (SELECT 1 FROM rm_scoring_runs WHERE batch_id=$1 AND status IN ('queued','running'))""",
                bid,
            )
            return
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            os.environ["RM_ARTIFACT_DIR"] = root
            model_dir = await asyncio.to_thread(
                download_model, model["artifact_key"], directory / "checkpoint"
            )
            reward_model = await asyncio.to_thread(RewardModel, model_dir)

            async def worker(path, run_id):
                # Inference runs off the event loop; persist throttled batch
                # events on that loop without giving torch a DB connection.
                events = asyncio.Queue()
                loop = asyncio.get_running_loop()
                reporter = Reporter(
                    on_event=lambda event: loop.call_soon_threadsafe(events.put_nowait, event)
                )

                async def persist():
                    while (event := await events.get()) is not None:
                        await scoring_progress.save(run_id, event)

                writer = asyncio.create_task(persist())
                try:
                    await asyncio.to_thread(
                        score_run.run,
                        path,
                        model=reward_model,
                        model_dir=model_dir,
                        progress=reporter,
                    )
                finally:
                    events.put_nowait(None)
                    await writer

            for _ in runs:
                # Re-read priority between traces so a user pressing Run is
                # served next by the already-warm checkpoint, not last in line.
                run_id = await pool.fetchval(
                    """SELECT id FROM rm_scoring_runs WHERE batch_id=$1 AND owner_user_id=$2
                    AND reward_model_id=$3 AND status='queued'
                    ORDER BY requested_at NULLS LAST,created_at,id LIMIT 1""",
                    bid,
                    model["owner_user_id"],
                    model["id"],
                )
                if run_id is None:
                    break
                claimed = await pool.fetchval(
                    """UPDATE rm_scoring_runs r SET status='running',started_at=now()
                    WHERE r.id=$1 AND r.status='queued' AND EXISTS
                    (SELECT 1 FROM rm_scoring_batches b WHERE b.id=r.batch_id AND b.status='running') RETURNING r.id""",
                    run_id,
                )
                if claimed is None:
                    continue
                try:
                    await jobs.run_scoring(run_id, worker=worker)
                except Exception as exc:
                    await pool.execute(
                        "UPDATE rm_scoring_runs SET status='failed',error=$2,finished_at=now() WHERE id=$1 AND status='running'",
                        run_id,
                        str(exc)[-2000:],
                    )
                finally:
                    # Only one trace's inputs/results reside on disk at a time.
                    shutil.rmtree(jobs.job_dir(run_id), ignore_errors=True)
        failures = await pool.fetchval(
            "SELECT count(*) FROM rm_scoring_runs WHERE batch_id=$1 AND status='failed'", bid
        )
        await pool.execute(
            """UPDATE rm_scoring_batches SET status=$2,error=$3,finished_at=now()
            WHERE id=$1 AND status='running' AND NOT EXISTS
            (SELECT 1 FROM rm_scoring_runs WHERE batch_id=$1 AND status IN ('queued','running'))""",
            bid,
            "failed" if failures else "succeeded",
            f"{failures} trace(s) failed" if failures else None,
        )
    except (Exception, asyncio.CancelledError) as exc:
        await precompute.fail(bid, str(exc) or "Background scoring was cancelled or timed out")
        raise
    finally:
        if previous is None:
            os.environ.pop("RM_ARTIFACT_DIR", None)
        else:
            os.environ["RM_ARTIFACT_DIR"] = previous
        await database.close_db()


def dispatch(batch_id: str) -> str:
    app = modal.App("stash-eager-model-scoring", image=training_image)
    secret = modal.Secret.from_dict(
        {key: os.environ[key] for key in (*SECRET_KEYS, "DATABASE_URL") if key in os.environ}
    )
    remote = app.function(gpu="A10G", memory=8192, timeout=TIMEOUT_SECONDS, secrets=[secret])(score)
    with app.run(detach=True):
        return remote.spawn(batch_id).object_id
