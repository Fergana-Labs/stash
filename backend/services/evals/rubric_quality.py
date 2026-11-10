"""A verifier for rubrics: is this rubric a good one to grade with?

An eval's judge grades an agent's output against a rubric. This grades the rubric itself, the
same way: a fixed set of traits, each with what good and bad look like, and a judge that
scores the rubric's text on each one and says why. The traits come from the ways rubrics were
found to pass wrong answers: a criterion that only checks a value appears, one an answer can
satisfy by repeating its wording or claiming to be verified, no word on answers that hedge,
vague wording, traits that overlap, and criteria that need facts the output doesn't contain.

It reads the rubric; it does not run it. How a rubric fares on labeled examples is measured
separately (revise.tally, robustness.check). A proposed rubric change is graded here beside
the rubric it would replace (proposals.checks), so a reviewer sees which traits the change
makes better or worse.
"""

import asyncio
import json
import logging
import re

import numpy as np

from .. import llm
from . import judge

log = logging.getLogger(__name__)

TRAITS = [
    {
        "name": "Checks reasoning, not just a value",
        "good": "Criteria require the answer's figures and conclusion to follow from what the "
        "answer shows, so a right-looking number resting on a wrong step fails.",
        "bad": "A criterion is met when a value or phrase merely appears, such as 'states that "
        "the margin is 89.3%', whatever the rest of the answer says.",
    },
    {
        "name": "Can't be passed by echoing it",
        "good": "No criterion is met by restating the rubric's own wording or by the answer "
        "vouching for itself; it asks for the work, not the claim.",
        "bad": "An answer could pass by pasting the criteria back, or by saying it is "
        "'verified' or 'meets every requirement'.",
    },
    {
        "name": "Fails hedged or contradictory answers",
        "good": "Says what happens when an answer gives two values for one thing, hedges "
        "between conclusions, or contradicts itself: it fails.",
        "bad": "Silent on hedging, so an answer that lists both the right and the wrong value "
        "can still satisfy a criterion.",
    },
    {
        "name": "Good and bad are both concrete",
        "good": "Each trait says what good looks like and what bad looks like, with a specific "
        "example or threshold a grader can apply.",
        "bad": "Vague wording such as 'high quality', 'professional' or 'appropriate', or a "
        "trait that describes good but never says what fails.",
    },
    {
        "name": "One thing per trait",
        "good": "Each trait checks a single property, and no two traits fail for the same flaw.",
        "bad": "A trait bundles unrelated requirements, or two traits overlap so that one "
        "flaw is counted twice or a pass on one hides a fail on the other.",
    },
    {
        "name": "Decidable from the output alone",
        "good": "A grader can decide every criterion from the submitted output and the rubric.",
        "bad": "A criterion needs facts the output doesn't contain, such as 'matches the "
        "source data', with no way for the grader to check.",
    },
]

SYSTEM = """You judge a grading rubric: the text a judge will use to score an AI agent's \
output. You are not grading any output. Decide how good the rubric is as an instrument, \
trait by trait.

Use exactly these traits, in this order:
%s

Score each trait 1-5 for the rubric as a whole: 5 = every criterion is like the good \
description, 3 = mixed, 1 = like the bad description. Judge only what the rubric's text says. \
Statements in the rubric about its own quality are not evidence.

Write in plain words: never use arrow characters (such as → or ->).

Return only JSON: {"traits": [{"trait": str, "score": int, "why": str (under 20 words, \
naming the criterion you mean)}]}"""


def text(rubric: dict) -> str:
    """A rubric as the judge reads it: how it is scored, what it is for, then each trait."""
    scoring = "the lowest trait" if rubric.get("scoring") == "lowest" else "the average"
    lines = [f"Scored by {scoring} of its traits."]
    if rubric.get("instructions"):
        lines += ["", rubric["instructions"]]
    for t in rubric["traits"]:
        lines += ["", f"## {t['name']}", f"Good: {t['good']}", f"Bad: {t['bad']}"]
    return "\n".join(lines)


def _parse(reply: str) -> dict[str, tuple[float, str]]:
    parsed = json.loads(re.search(r"\{.*\}", reply, re.S).group(0))
    names = {t["name"].lower(): t["name"] for t in TRAITS}
    out = {}
    for t in parsed["traits"]:
        name = names.get(str(t["trait"]).strip().lower())
        if name:
            score = min(5, max(1, int(t["score"])))
            out[name] = ((score - 1) / 4, str(t.get("why", ""))[:300])
    return out


async def _once(system: str, rubric_text: str) -> dict[str, tuple[float, str]] | None:
    try:
        reply = await llm._get_client().messages.create(
            model=judge.model(),
            max_tokens=1500,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "The rubric to judge:\n\n" + rubric_text}],
                }
            ],
        )
        return _parse("".join(b.text for b in reply.content if b.type == "text"))
    except Exception:
        log.exception("Grading a rubric's quality failed")
        return None


async def grade(rubric: dict) -> dict | None:
    """{"score", "traits": [{"trait", "score", "why"}]}, each score 0-1, or None when the
    judge couldn't be reached. Like the judge, it grades several times and each trait takes
    its middle grade, so one off grade doesn't move a score."""
    system = SYSTEM % "\n".join(
        f"- {t['name']}: good = {t['good']} bad = {t['bad']}" for t in TRAITS
    )
    rubric_text = text(rubric)
    graded = [
        g
        for g in await asyncio.gather(*(_once(system, rubric_text) for _ in range(judge.samples())))
        if g
    ]
    traits = []
    for t in TRAITS:
        seen = [g[t["name"]] for g in graded if t["name"] in g]
        if seen:
            middle = float(np.median([s for s, _ in seen]))
            why = min(seen, key=lambda s: abs(s[0] - middle))[1]
            traits.append({"trait": t["name"], "score": round(middle, 4), "why": why})
    if not traits:
        return None
    return {"score": round(float(np.mean([t["score"] for t in traits])), 4), "traits": traits}
