"""Mine eval criteria from what users actually did: corrections, repeats and frustration.

Users rarely label anything, but they vote all the time: a correction says the
answer before it was wrong and how; a repeated request says it missed; a
negative reply says something about it grated. From the traces of a cohort
(say, the frustrated ones), each such reaction is paired with the agent output
it reacted to, and Claude proposes rubric questions about the observable
properties those reactions keep pointing at. They are candidates: the owner
adds the ones they agree with to the draft, and the Rubric Builder takes it
from there.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import BaseModel, Field

from ...database import get_pool
from .. import llm
from ..behaviors import cohorts
from . import service

MAX_VOTES = 40
CLIP = 600
REACTIONS = {"correction", "repeat_request"}


def _clip(text: str | None) -> str:
    text = (text or "").strip()
    return text if len(text) <= CLIP else text[: CLIP - 1] + "…"


async def votes(trace_ids: list[UUID]) -> list[dict]:
    """(agent output, user reaction) pairs where the user corrected, repeated or pushed back."""
    pool = get_pool()
    out: list[dict] = []
    for trace_id in trace_ids:
        labels = await pool.fetchval(
            "SELECT labels FROM rm_step_labels WHERE trace_id = $1", trace_id
        )
        if not labels:
            continue
        steps = {
            r["idx"]: r
            for r in await pool.fetch(
                "SELECT idx, role, content, tool_name FROM rm_trace_steps WHERE trace_id = $1",
                trace_id,
            )
        }
        for key in sorted(labels, key=int):
            label = labels[key]
            if label.get("actor") != "user":
                continue
            if label.get("intent") not in REACTIONS and label.get("sentiment") != "negative":
                continue
            idx = int(key)
            previous = next(
                (steps[i] for i in range(idx - 1, -1, -1) if i in steps and steps[i]["role"] == "assistant" and not steps[i]["tool_name"] and (steps[i]["content"] or "").strip()),
                None,
            )  # fmt: skip
            if previous is None or idx not in steps:
                continue
            out.append(
                {
                    "reaction": label.get("intent")
                    if label.get("intent") in REACTIONS
                    else "negative",
                    "agent_said": _clip(previous["content"]),
                    "user_replied": _clip(steps[idx]["content"]),
                }
            )
            if len(out) >= MAX_VOTES:
                return out
    return out


class Mined(BaseModel):
    rationale: str
    questions: list[service._QuestionDraft] = Field(min_length=1, max_length=4)


SYSTEM = (
    "You turn users' implicit feedback on an AI agent into evaluation criteria. Each item pairs an agent "
    "answer with the user's reaction: a correction, a repeated request, or a negative reply. Find the recurring "
    "properties of the answers that users reacted against, and write rubric questions a judge can answer about a "
    "new answer to catch them. Prefer questions the existing rubric does not already ask. "
    + service.QUESTION_FORMAT
)


async def suggest(owner_id: UUID, model_id: UUID, by: str, key: str, days: int = 30) -> dict:
    model = await service._model(owner_id, model_id)
    version = await service._load_version(model["draft_version_id"] or model["active_version_id"])
    members = await cohorts.members(owner_id, by, key, days)
    found = await votes([t["id"] for t in members])
    if not found:
        raise service.Conflict(
            "No corrections, repeats or negative replies in this cohort to learn from"
        )
    result = await llm.complete_structured(
        prompt=(
            f"WHAT THE EVAL JUDGES:\n{version['description']}\n\n"
            f"EXISTING RUBRIC:\n{json.dumps(version['rubric'], ensure_ascii=False)}\n\n"
            "IMPLICIT FEEDBACK:\n" + "\n".join(json.dumps(v, ensure_ascii=False) for v in found)
        ),
        system=SYSTEM,
        output_model=Mined,
        tier=llm.ModelTier.QUALITY,
        max_tokens=3000,
    )
    taken = {q["id"] for q in version["rubric"]}
    return {
        "cohort": {"by": by, "key": key, "traces": len(members)},
        "votes": len(found),
        "examples": found[:5],
        "rationale": result.rationale,
        "questions": [service._question(q, taken) for q in result.questions],
    }
