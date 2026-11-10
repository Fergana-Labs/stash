"""Rubric quality: a rubric is graded by a Stash eval, like any other piece of work.

An eval can name another eval that grades its rubrics (intuition_models.rubric_eval_id). That
eval is an ordinary one: its examples are rubrics a person labeled good or bad, its own rubric
is written from them and says what makes a rubric a good one to grade with, and it improves
the way every eval does. When a rubric change is proposed, the rubric in use and the proposed
rubric are each written out as text and scored with it (proposals.checks), so a reviewer sees
which of its traits the change makes better or worse. Each score is an ordinary scored call on
the grading eval, listed with its other calls.

It reads the rubric; it does not run it. How a rubric fares on labeled examples is measured
separately (revise.tally, robustness.check).
"""

import asyncio
from uuid import UUID

from ...database import get_pool
from . import service

CALLER = "rubric change"


def text(rubric: dict) -> str:
    """A rubric as it is submitted for grading: how it is scored, what it is for, then each
    trait with what good and bad look like."""
    scoring = "the lowest trait" if rubric.get("scoring") == "lowest" else "the average"
    lines = [f"Scored by {scoring} of its traits."]
    if rubric.get("instructions"):
        lines += ["", rubric["instructions"]]
    for t in rubric["traits"]:
        lines += ["", f"## {t['name']}", f"Good: {t['good']}", f"Bad: {t['bad']}"]
    return "\n".join(lines)


async def set_eval(owner: UUID, eval_id: UUID, rubric_eval_id: UUID | None) -> dict:
    """Name the eval that grades this eval's rubrics, or stop naming one. Both are the
    person's own, and an eval can't grade its own rubric."""
    await service._owned(owner, eval_id)
    if rubric_eval_id is not None:
        if rubric_eval_id == eval_id:
            raise ValueError("An eval can't grade its own rubric")
        await service._owned(owner, rubric_eval_id)
    await get_pool().execute(
        "UPDATE intuition_models SET rubric_eval_id=$2, updated_at=now() WHERE id=$1",
        eval_id,
        rubric_eval_id,
    )
    return {"rubric_eval_id": rubric_eval_id}


async def grade(model_id: UUID, base: dict, candidate: dict) -> dict | None:
    """Score the rubric in use and the proposed rubric with the eval that grades this eval's
    rubrics: {"eval": {id, name, version}, "before", "after"}, each side {"score", "traits":
    [{"trait", "score", "why"}], "call_id"}. None when no eval is named or it isn't built."""
    grader = await get_pool().fetchrow(
        """SELECT q.id, q.name, q.owner_user_id, q.traits FROM intuition_models m
           JOIN intuition_models q ON q.id = m.rubric_eval_id WHERE m.id=$1""",
        model_id,
    )
    if grader is None or not grader["traits"]:
        return None

    async def one(rubric: dict, which: str) -> dict:
        result = await service.score(
            grader["owner_user_id"],
            grader["id"],
            text=text(rubric),
            caller=CALLER,
            metadata={"eval_id": str(model_id), "rubric": which},
        )
        return {
            "score": result["score"],
            "traits": [
                {"trait": t["trait"], "score": t["score"], "why": t.get("why", "")}
                for t in result["traits"]
            ],
            "call_id": str(result["call_id"]),
            "version": result["rubric_version"],
        }

    before, after = await asyncio.gather(one(base, "in use"), one(candidate, "proposed"))
    return {
        "eval": {"id": str(grader["id"]), "name": grader["name"], "version": after.pop("version")},
        "before": {k: v for k, v in before.items() if k != "version"},
        "after": after,
    }
