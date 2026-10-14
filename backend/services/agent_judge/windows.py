"""Agent-judged behaviors: high-stakes patterns worth an investigation, not a glance.

For a behavior whose detector is the Agent Judge, each unread segment most
like the definition is judged with the trace around it as context; a "yes"
becomes a hit whose window spans the steps the workers cited. Investigations
are expensive, so a pass reads few segments and the scanner comes back for
the rest.
"""

from __future__ import annotations

from uuid import UUID

from ..behaviors import detect as model_detect
from . import judge

SEGMENTS_PER_PASS = 3
CONTEXT_STEPS = 6
THRESHOLD = 0.5


def question(behavior: dict) -> dict:
    prompt = f"Do the steps in the judged window show this {behavior['actor']} behavior? {behavior['definition']}"
    return {
        "id": "shows",
        "type": "noul",
        "prompt": prompt[:2000],
        "criteria": {
            "true": "The window clearly shows the behavior",
            "false": "It does not, or only arguably",
        },
    }


async def detect(
    behavior: dict, trace_id: UUID, segments: list[dict], seen: set[str]
) -> tuple[list[dict], set[str]]:
    from ..intuition import builder

    todo = await model_detect.rank(behavior, [s for s in segments if s["content_hash"] not in seen])
    if not todo:
        return [], set(seen)
    item, _ = await builder.trace_input(behavior["owner_user_id"], trace_id)
    reviews = await model_detect.reviewed(behavior)
    version = {
        "description": model_detect.describe(behavior) + ("\n\n" + reviews if reviews else ""),
        "model_id": None,
    }
    hits, read = [], set(seen)
    for seg in todo[:SEGMENTS_PER_PASS]:
        lo, hi = seg["start_idx"], seg["end_idx"]
        window_item = {
            **item,
            "steps": [
                s for s in item["steps"] if lo - CONTEXT_STEPS <= s["index"] <= hi + CONTEXT_STEPS
            ],
            "window": {"start": lo, "end": hi},
        }
        result = await judge.judge(
            version, [question(behavior)], window_item, behavior["owner_user_id"]
        )
        read.add(seg["content_hash"])
        p = result["answers"]["shows"]["probabilities"]["true"]
        if p < THRESHOLD:
            continue
        cited = [
            e
            for f in result["report"]["findings"]
            if f["finding"]["verdict"] == "supports"
            for e in f["finding"]["evidence"]
            if lo <= e["idx"] <= hi
        ]
        idxs = [e["idx"] for e in cited] or [lo, hi]
        hits.append(
            {
                "start_idx": min(idxs),
                "end_idx": max(idxs),
                "confidence": p,
                "evidence": cited[:6],
                "note": result["report"]["answers"]["shows"]["rationale"][:400],
            }
        )
    return hits, read
