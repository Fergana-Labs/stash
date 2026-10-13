"""Persistent one-minute debounce; existing rubric/features survive head-only updates."""

from uuid import UUID

from ...database import get_pool
from . import builder, service


async def status(owner_id: UUID, model_id: UUID) -> dict | None:
    await service._model(owner_id, model_id)
    row = await get_pool().fetchrow("SELECT * FROM intuition_updates WHERE model_id=$1", model_id)
    return dict(row) if row else None


async def enable(owner_id: UUID, model_id: UUID) -> dict:
    model = await service._model(owner_id, model_id)
    active = await service._load_version(model["active_version_id"])
    draft = await service._load_version(model["draft_version_id"])
    examples = await service.list_examples(owner_id, model_id)
    ready = (
        len(
            {
                e["label"]
                for e in examples
                if e["label"] and not e["needs_review"] and e["split"] == "train"
            }
        )
        >= 2
    )
    current = bool(active and not draft)
    await get_pool().execute(
        """INSERT INTO intuition_updates(model_id,state,completed_revision,rubric_dirty)
        VALUES($1,$2,$3,$4) ON CONFLICT(model_id) DO NOTHING""",
        model_id,
        "idle" if current else "pending" if ready else "needs_examples",
        1 if current else 0,
        not bool(active)
        or bool(draft and active and draft["description"] != active["description"]),
    )
    return await status(owner_id, model_id)


async def request(
    owner_id: UUID, model_id: UUID, *, rubric_dirty: bool = False, example_id: UUID | None = None
) -> None:
    """Mark before mutating inputs so a running update cannot publish obsolete work."""
    await service._model(owner_id, model_id)
    if example_id is not None:
        example = await get_pool().fetchrow(
            "SELECT label,note FROM intuition_examples WHERE model_id=$1 AND id=$2",
            model_id,
            example_id,
        )
        if example is None:
            raise service.NotFound("Example not found")
        rubric_dirty = rubric_dirty or (
            example["label"] is None and example["note"] == "Reference material"
        )
    await get_pool().execute(
        """UPDATE intuition_updates SET revision=revision+1,
        rubric_dirty=rubric_dirty OR $2, run_after=now()+interval '1 minute',
        state=CASE WHEN state='running' THEN state ELSE 'pending' END,
        error=NULL, attempts=0 WHERE model_id=$1""",
        model_id,
        rubric_dirty,
    )


async def retry(owner_id: UUID, model_id: UUID) -> dict:
    await request(owner_id, model_id)
    return await status(owner_id, model_id)


async def _stage(model_id: UUID, stage: str) -> None:
    await get_pool().execute(
        "UPDATE intuition_updates SET stage=$2,started_at=now() WHERE model_id=$1", model_id, stage
    )


async def run(model_id: UUID) -> None:
    pool = get_pool()
    job = await pool.fetchrow(
        """UPDATE intuition_updates SET state='running',started_at=now(),error=NULL,
        attempts=attempts+1 WHERE model_id=$1 AND run_after<=now()
        AND (state IN ('pending','queued') OR (state='running' AND started_at<now()-interval '15 minutes'))
        RETURNING *""",
        model_id,
    )
    if job is None:
        return
    owner_id = await pool.fetchval(
        "SELECT owner_user_id FROM intuition_models WHERE id=$1", model_id
    )
    revision = job["revision"]
    try:
        await _stage(model_id, "Preparing examples")
        examples = await builder.reserve_holdout(owner_id, model_id)
        train = [
            e for e in examples if e["split"] == "train" and e["label"] and not e["needs_review"]
        ]
        model = await service._model(owner_id, model_id)
        if not train or (model["output_type"] == "choice" and len({e["label"] for e in train}) < 2):
            await pool.execute(
                """UPDATE intuition_updates SET state=CASE WHEN revision=$2 THEN 'needs_examples'
                ELSE 'pending' END, stage='Add good and bad examples',started_at=NULL WHERE model_id=$1""",
                model_id,
                revision,
            )
            return
        draft = await service.ensure_draft(owner_id, model_id)
        active = await service._load_version(model["active_version_id"])
        if job["rubric_dirty"] or not draft["rubric"]:
            await builder.prepare(owner_id, model_id, require_holdout=False)
            await _stage(model_id, "Generating criteria")
            proposed = await service.draft_rubric(owner_id, model_id, count=5, guidance="")
            await service.update_draft(owner_id, model_id, {"rubric": proposed["rubric"]})
            await pool.execute(
                "UPDATE intuition_updates SET rubric_dirty=false WHERE model_id=$1 AND revision=$2",
                model_id,
                revision,
            )
        elif active:
            # Keep judge context fixed so only new inputs need remote grading.
            # Labels/corrections change the cheap head, not cached judge features.
            await pool.execute(
                "UPDATE intuition_versions SET seed_snapshot=$2 WHERE id=$1",
                draft["id"],
                await service._seeds(active),
            )
        await _stage(model_id, "Scoring new examples")
        for _ in range(100):
            current = await pool.fetchval(
                "SELECT revision FROM intuition_updates WHERE model_id=$1", model_id
            )
            if current != revision:
                raise service.Conflict("Examples changed; waiting for the latest update")
            graded = await service.grade_pending(owner_id, model_id, limit=50, reviewed_only=True)
            if graded["failed"]:
                raise service.Conflict("; ".join(graded["errors"]) or "Could not score examples")
            if not graded["remaining"]:
                break
            if not graded["graded"]:
                raise service.Conflict("Scoring made no progress")
        else:
            raise service.Conflict("Too many pending examples; update will retry")
        await _stage(model_id, "Updating calibration")
        await service.fit(owner_id, model_id, train_on="train", calibrate=True)
        await service.promote(owner_id, model_id, force=True, expected_update_revision=revision)
        await pool.execute(
            """UPDATE intuition_updates SET completed_revision=$2,finished_at=now(),
            rubric_dirty=CASE WHEN revision=$2 THEN false ELSE rubric_dirty END,
            state=CASE WHEN revision=$2 THEN 'idle' ELSE 'pending' END,
            stage=NULL,started_at=NULL,error=NULL WHERE model_id=$1""",
            model_id,
            revision,
        )
    except Exception as exc:
        await pool.execute(
            """UPDATE intuition_updates SET
            state=CASE WHEN revision<>$2 OR attempts<3 THEN 'pending' ELSE 'failed' END,
            run_after=CASE WHEN revision=$2 THEN now()+interval '1 minute' ELSE run_after END,
            error=CASE WHEN revision=$2 THEN $3 ELSE NULL END,stage=NULL,started_at=NULL
            WHERE model_id=$1""",
            model_id,
            revision,
            str(exc)[:2000],
        )
