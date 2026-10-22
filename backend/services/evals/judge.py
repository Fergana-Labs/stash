"""The judge: Claude grades an agent's output against the eval's examples.

It sees the eval's good and bad examples (images as pixels, with close-ups of good
images so line and texture are visible), the traits the build wrote, notes people left
on earlier calls, and the submission: the agent's trace for context and its output. It
grades each trait 1-5, explains, and names fixes. The score is the mean grade scaled to
0-1.

Why this and not a classifier: on Henry's judgments (draw-agent-toy/bench) a classifier
over image embeddings ranked his liked drafts below his disliked ones (AUC 0.19) and
scored image-model fakes 0.98-1.00; these trait grades separated them (AUC 0.95, 0.98 on
agent drafts) and moved about 0.05 when the same image was scored twice.
"""

import json
import logging
import random
import re
from uuid import UUID

import numpy as np

from ...config import settings
from ...database import get_pool
from .. import llm
from . import items

logger = logging.getLogger(__name__)
GOOD_REFS = 6
BAD_REFS = 3
CLOSEUPS = 2
NOTES = 12
ATTEMPTS = 2


class JudgeUnavailable(RuntimeError):
    """The score could not be computed; callers should retry rather than get a made-up number."""


SYSTEM = """You judge an AI agent's output against what one person wants, as shown by \
examples they marked good and bad. You get their examples, the traits that separate good \
from bad here, notes they wrote about earlier outputs, and the submission: the agent's \
trace (what it was asked and did, for context) and its output. Judge the output.

Grade the output on each trait from 1 to 5:
5 = as good as their good examples on this trait
4 = close; a careful eye would spot small differences
3 = recognizably aiming for it, clearly short of their good examples
2 = only loosely related
1 = absent, or like their bad examples
%s
Ignore signatures, handles, watermarks and logos, and never ask for one.

Return only JSON: {"traits": [{"trait": str, "score": int, "why": str (under 20 words)}], \
"summary": str (one or two sentences: the explanation of the grade), "fixes": [{"issue": str, \
"fix": str}] (1-4, most important first; what to change and what the good examples do \
instead), "keep": [str] (0-2)}"""

TRAITS_GIVEN = """Use exactly these traits, in this order:
%s"""
TRAITS_CHOSEN = """Choose the 5-8 traits that most separate the good examples from the bad \
ones (or, with only good examples, that define them)."""


def model() -> str:
    return settings.EVAL_JUDGE_MODEL


def _traits_text(traits: list[dict]) -> str:
    return "\n".join(
        f"- {t['name']}: good = {t.get('good', '')}; bad = {t.get('bad', '')}" for t in traits
    )


async def references(model_id: UUID, exclude: UUID | None = None) -> tuple[list[dict], list[dict]]:
    """The good and bad examples shown to the judge: a fixed sample per eval."""
    rows = await get_pool().fetch(
        "SELECT id, item, label FROM intuition_examples WHERE model_id=$1 AND label IN ('good','bad') ORDER BY created_at",
        model_id,
    )
    rows = [r for r in rows if r["id"] != exclude]
    rng = random.Random(str(model_id))
    good = [r for r in rows if r["label"] == "good"]
    bad = [r for r in rows if r["label"] == "bad"]
    pick = lambda rs, n: rng.sample(rs, min(n, len(rs)))  # noqa: E731
    as_item = lambda r: r["item"] if isinstance(r["item"], dict) else json.loads(r["item"])  # noqa: E731
    return [as_item(r) for r in pick(good, GOOD_REFS)], [as_item(r) for r in pick(bad, BAD_REFS)]


async def context(model_id: UUID, exclude: UUID | None = None) -> list[dict]:
    """Everything about the eval the judge reads before the submission."""
    row = await get_pool().fetchrow(
        "SELECT name, instructions, traits FROM intuition_models WHERE id=$1", model_id
    )
    good, bad = await references(model_id, exclude)
    content: list[dict] = [{"type": "text", "text": f"Eval: {row['name']}"}]
    if row["instructions"]:
        content.append({"type": "text", "text": f"What they want judged: {row['instructions']}"})
    for i, item in enumerate(good, 1):
        content += [{"type": "text", "text": f"Good example {i}:"}, *await items.blocks(item, 512)]
    closeups = [data for item in good for data in await items.image_bytes(item)][:CLOSEUPS]
    if closeups:
        content.append({"type": "text", "text": "Full-resolution close-ups from good examples:"})
        content += [items.closeup(d) for d in closeups]
    for i, item in enumerate(bad, 1):
        content += [{"type": "text", "text": f"Bad example {i}:"}, *await items.blocks(item, 512)]
    notes = await get_pool().fetch(
        """SELECT label, note FROM intuition_examples WHERE model_id=$1 AND note<>''
        ORDER BY created_at DESC LIMIT $2""",
        model_id,
        NOTES,
    )
    if notes:
        content.append(
            {
                "type": "text",
                "text": "Their notes on earlier outputs:\n"
                + "\n".join(f"- ({n['label']}) {n['note']}" for n in notes),
            }
        )
    return content


def _parse(text: str) -> dict:
    parsed = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    traits = [
        {
            "trait": str(t["trait"])[:80],
            "score": int(t["score"]),
            "why": str(t.get("why", ""))[:300],
        }
        for t in parsed.get("traits", [])
        if isinstance(t, dict) and 1 <= int(t.get("score", 0)) <= 5
    ]
    if not traits:
        raise ValueError("no trait grades")
    return {
        "score": round((float(np.mean([t["score"] for t in traits])) - 1) / 4, 4),
        "traits": traits,
        "explanation": str(parsed.get("summary", ""))[:1000],
        "fixes": [
            {"issue": str(f.get("issue", ""))[:600], "fix": str(f.get("fix", ""))[:600]}
            for f in parsed.get("fixes", [])[:4]
            if isinstance(f, dict)
        ],
        "keep": [str(k)[:300] for k in parsed.get("keep", [])[:2]],
    }


async def grade(model_id: UUID, submission: dict, exclude: UUID | None = None) -> dict:
    """{"score", "traits", "explanation", "fixes", "keep"}; raises JudgeUnavailable."""
    traits = await get_pool().fetchval("SELECT traits FROM intuition_models WHERE id=$1", model_id)
    system = SYSTEM % (TRAITS_GIVEN % _traits_text(traits) if traits else TRAITS_CHOSEN)
    content = await context(model_id, exclude)
    content += [
        {"type": "text", "text": "The submission to judge:"},
        *await items.blocks(submission, 1024),
    ]
    for attempt in range(ATTEMPTS):
        try:
            reply = await llm._get_client().messages.create(
                model=model(),
                max_tokens=3000,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            return _parse("".join(b.text for b in reply.content if b.type == "text"))
        except Exception:
            logger.warning(
                "Eval judge failed for %s (attempt %d)", model_id, attempt + 1, exc_info=True
            )
    raise JudgeUnavailable("Couldn't score this right now; try again")
