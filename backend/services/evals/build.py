"""Build a judge eval: write its traits from the examples, then check it against them.

1. Traits: Claude studies the good examples (and the bad ones, if any) and writes the
   5-8 traits that separate good from bad, each with what good and bad look like here.
   Writing them once keeps every score on the same scale.
2. Check: with both good and bad examples, each one (up to CHECK_EACH per label) is
   graded with itself left out of the references; the build records how often a good
   example scores at least 0.5 and a bad one below it, and how often a good example
   outscores a bad one.
"""

import asyncio
import json
import re
from uuid import UUID

from ...database import get_pool
from .. import llm
from . import items, judge

TRAIT_GOOD = 10
TRAIT_BAD = 6
CHECK_EACH = 12
CONCURRENCY = 4

TRAITS_SYSTEM = """You study examples someone marked good and bad, so an AI judge can grade \
new outputs the way they would. Write the 5-8 traits that most separate good from bad \
(with only good examples, the traits that define them). Each trait names one property you \
can see in an output, never the verdict itself, and says concretely what good and bad look \
like here: specific enough that two judges would grade the same output the same way. \
Nothing about signatures, handles or watermarks.

Return only JSON: {"summary": str (one sentence: what these examples are and what makes one \
good), "traits": [{"name": str (2-4 words), "good": str, "bad": str}]}"""


async def _set(model_id: UUID, **build) -> None:
    await get_pool().execute(
        "UPDATE intuition_models SET build = COALESCE(build, '{}'::jsonb) || $2::jsonb, updated_at=now() WHERE id=$1",
        model_id,
        build,
    )


async def _examples(model_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, item, label FROM intuition_examples WHERE model_id=$1 AND label IN ('good','bad') ORDER BY created_at",
        model_id,
    )
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "item": r["item"] if isinstance(r["item"], dict) else json.loads(r["item"]),
        }
        for r in rows
    ]


async def write_traits(model_id: UUID, examples: list[dict]) -> dict:
    row = await get_pool().fetchrow(
        "SELECT name, instructions FROM intuition_models WHERE id=$1", model_id
    )
    content: list[dict] = [{"type": "text", "text": f"Eval: {row['name']}"}]
    if row["instructions"]:
        content.append({"type": "text", "text": f"What they want judged: {row['instructions']}"})
    good = [e for e in examples if e["label"] == "good"][:TRAIT_GOOD]
    bad = [e for e in examples if e["label"] == "bad"][:TRAIT_BAD]
    for i, e in enumerate(good, 1):
        content += [
            {"type": "text", "text": f"Good example {i}:"},
            *await items.blocks(e["item"], 512),
        ]
    closeups = [d for e in good for d in await items.image_bytes(e["item"])][:4]
    if closeups:
        content.append({"type": "text", "text": "Full-resolution close-ups from good examples:"})
        content += [items.closeup(d) for d in closeups]
    for i, e in enumerate(bad, 1):
        content += [
            {"type": "text", "text": f"Bad example {i}:"},
            *await items.blocks(e["item"], 512),
        ]
    content.append({"type": "text", "text": "Write the traits now."})
    reply = await llm._get_client().messages.create(
        model=judge.model(),
        max_tokens=4000,
        system=TRAITS_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in reply.content if b.type == "text")
    parsed = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    traits = [
        {
            "name": str(t["name"])[:60],
            "good": str(t.get("good", ""))[:400],
            "bad": str(t.get("bad", ""))[:400],
        }
        for t in parsed.get("traits", [])[:8]
        if isinstance(t, dict) and t.get("name")
    ]
    if not traits:
        raise ValueError("Could not write traits from these examples")
    return {"summary": str(parsed.get("summary", ""))[:500], "traits": traits}


def _agreement(scored: list[tuple[str, float]]) -> dict:
    good = [s for label, s in scored if label == "good"]
    bad = [s for label, s in scored if label == "bad"]
    right = [s >= 0.5 for s in good] + [s < 0.5 for s in bad]
    pairs = [(g > b) + 0.5 * (g == b) for g in good for b in bad]
    return {
        "checked": len(scored),
        "agreement": round(sum(right) / len(right), 3) if right else None,
        "good_above_bad": round(sum(pairs) / len(pairs), 3) if pairs else None,
    }


async def run(model_id: UUID) -> None:
    examples = await _examples(model_id)
    if not any(e["label"] == "good" for e in examples):
        raise ValueError("Add some good examples first")
    await _set(model_id, stage="traits", done=0, total=0, error=None)
    written = await write_traits(model_id, examples)
    await get_pool().execute(
        "UPDATE intuition_models SET traits=$2::jsonb, updated_at=now() WHERE id=$1",
        model_id,
        written["traits"],
    )
    await _set(model_id, summary=written["summary"])

    checks = [e for e in examples if e["label"] == "good"][:CHECK_EACH] + [
        e for e in examples if e["label"] == "bad"
    ][:CHECK_EACH]
    if not any(e["label"] == "bad" for e in checks):
        await _set(
            model_id,
            stage="done",
            metrics={"checked": 0, "agreement": None, "good_above_bad": None},
        )
        return
    await _set(model_id, stage="checking", done=0, total=len(checks))
    gate = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def one(e: dict) -> tuple[str, float] | None:
        nonlocal done
        async with gate:
            try:
                result = await judge.grade(model_id, e["item"], exclude=e["id"])
            except judge.JudgeUnavailable:
                return None
        done += 1
        await _set(model_id, done=done)
        return e["label"], result["score"]

    scored = [s for s in await asyncio.gather(*(one(e) for e in checks)) if s]
    await _set(model_id, stage="done", metrics=_agreement(scored))
