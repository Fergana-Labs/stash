"""Owner-scoped playground jobs, separate from imported traces and training data."""

import json
import math
from uuid import UUID

from fastapi import HTTPException

from ...database import get_pool
from . import jobs


async def model_for_owner(owner: UUID, model_id: UUID):
    model = await get_pool().fetchrow(
        "SELECT * FROM rm_reward_models WHERE id = $1 AND owner_user_id = $2",
        model_id,
        owner,
    )
    if model is None:
        raise HTTPException(404, "Reward model not found")
    return model


async def expire_runs(owner: UUID) -> None:
    # Beyond Celery's 30-minute hard limit, a lost task cannot still be useful.
    await get_pool().execute(
        """UPDATE rm_playground_runs SET status = 'failed', finished_at = now(),
        error = 'Scoring timed out. Please try again.'
        WHERE owner_user_id = $1 AND status IN ('queued', 'running')
        AND created_at < now() - interval '35 minutes'""",
        owner,
    )


async def run_prediction(run_id: UUID) -> None:
    pool = get_pool()
    run = await pool.fetchrow(
        """SELECT r.*, m.artifact_key FROM rm_playground_runs r
        JOIN rm_reward_models m ON m.id = r.reward_model_id AND m.owner_user_id = r.owner_user_id
        WHERE r.id = $1 AND m.status = 'succeeded'""",
        run_id,
    )
    if run is None or not run["artifact_key"]:
        raise ValueError("Reward model checkpoint is unavailable")
    directory = jobs.job_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(
        json.dumps(
            {
                "kind": "playground",
                "reward_model_key": run["artifact_key"],
                "input": run["input"],
            }
        )
    )
    # Interactive inference always runs in the cloud, even for a checkpoint
    # originally trained locally. Never load model weights in the API process.
    await jobs.run_worker("rm_worker.modal_runner", directory)
    scores = json.loads((directory / "result.json").read_text()).get("scores")
    candidates = run["input"].get("texts", run["input"].get("responses"))
    if (
        not isinstance(scores, list)
        or len(scores) != len(candidates)
        or not all(type(s) in (int, float) and math.isfinite(s) for s in scores)
    ):
        raise ValueError("Checkpoint returned invalid reward scores")
    await pool.execute(
        """UPDATE rm_playground_runs SET status = 'succeeded', scores = $2, finished_at = now()
        WHERE id = $1 AND status = 'running'""",
        run_id,
        scores,
    )
