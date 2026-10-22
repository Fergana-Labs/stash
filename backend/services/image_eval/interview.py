"""The expert interview: after upload, Claude looks through the examples and asks the person
the few questions the images can't answer on their own (what is essential and what is
incidental, what imitators get wrong, what must never appear), and flags examples that don't
look like the rest. The answers are stored on the eval and given to every later step as the
person's own judgment: the style brief, the imitations it draws, and the written feedback.
"""

import json
import re
from uuid import UUID

from ...database import get_pool
from . import build, critic, service

LOOK_AT = 16
MAX_QUESTIONS = 4

SYSTEM = """You are interviewing an expert about a visual style they want an AI judge to \
enforce. You see numbered examples of the style. Your job is to ask the 2-4 questions whose \
answers the images cannot settle by themselves, and that would most change how a judge scores \
new work: which visible traits are essential and which are incidental, what people imitating \
it usually get wrong, what must never appear, how much variation is still "the style".

Each question names a concrete feature you can see in these images (a stroke, a color, a \
habit of composition or lettering), never a generic one ("is quality important?"). Give 2-4 \
short, mutually exclusive answer options that a person could tap without typing. Skip \
anything the images already make obvious, and never ask about signatures or watermarks. \
The person never sees the example numbers, so describe an example ("the one with the \
laser pointer") instead of citing its number.

Also list the numbers of any examples that do not look like the rest (a photo among \
drawings, a different medium, a different hand), so the person can leave them out.

Return only JSON: {"questions": [{"question": str, "why": str (under 12 words: what the \
answer changes), "options": [str]}], "outliers": [int]}"""


async def questions(owner: UUID, classifier_id: UUID) -> dict:
    """The interview for this eval, written on first request and then kept."""
    row = await service._owned(owner, classifier_id)
    if row["interview"] and row["interview"].get("questions") is not None:
        return row["interview"]
    examples = await get_pool().fetch(
        """SELECT id,image_key FROM image_eval_examples
        WHERE classifier_id=$1 AND label='liked' AND source='upload' ORDER BY created_at LIMIT $2""",
        classifier_id,
        LOOK_AT,
    )
    if not examples:
        raise ValueError("Add some images first")
    content: list = []
    for i, ex in enumerate(examples, 1):
        content += [
            {"type": "text", "text": f"Example {i}:"},
            critic.jpeg(await service._read(ex["image_key"]), 512),
        ]
    content.append({"type": "text", "text": "Write the interview now."})
    text = await build._ask(SYSTEM, content, 3000)
    match = re.search(r"\{.*\}", text, re.S)
    parsed = json.loads(match.group(0)) if match else {}
    asked = [
        {
            "question": str(q["question"])[:300],
            "why": str(q.get("why", ""))[:120],
            "options": [str(o)[:120] for o in q.get("options", [])][:4],
        }
        for q in parsed.get("questions", [])[:MAX_QUESTIONS]
        if isinstance(q, dict) and q.get("question")
    ]
    outliers = [
        str(examples[n - 1]["id"])
        for n in parsed.get("outliers", [])
        if isinstance(n, int) and 1 <= n <= len(examples)
    ]
    interview = {
        "questions": asked,
        "outliers": outliers,
        "answers": [],
        "left_out": [],
        "done": False,
    }
    await get_pool().execute(
        "UPDATE image_evals SET interview=$2, updated_at=now() WHERE id=$1",
        classifier_id,
        interview,
    )
    return interview


async def answer(
    owner: UUID, classifier_id: UUID, answers: list[dict], leave_out: list[UUID], skipped: bool
) -> dict:
    """Save the person's answers and drop the examples they said are not the style."""
    row = await service._owned(owner, classifier_id)
    interview = dict(row["interview"] or {"questions": [], "outliers": []})
    kept = [
        {"question": str(a["question"])[:300], "answer": str(a["answer"]).strip()[:1000]}
        for a in answers
        if str(a.get("answer", "")).strip()
    ]
    if leave_out:
        await get_pool().execute(
            "DELETE FROM image_eval_examples WHERE classifier_id=$1 AND id = ANY($2::uuid[]) AND source='upload'",
            classifier_id,
            leave_out,
        )
    interview.update(answers=kept, left_out=[str(x) for x in leave_out], done=True, skipped=skipped)
    await get_pool().execute(
        "UPDATE image_evals SET interview=$2, updated_at=now() WHERE id=$1",
        classifier_id,
        interview,
    )
    return await service.get(owner, classifier_id)


def told(interview: dict | None) -> str:
    """The person's answers, phrased for a prompt; empty when they gave none."""
    answers = (interview or {}).get("answers") or []
    if not answers:
        return ""
    lines = "\n".join(f"- Q: {a['question']}\n  A: {a['answer']}" for a in answers)
    return (
        "What the person told you about this style (their expert judgment; it overrides "
        f"anything you infer from the images):\n{lines}"
    )
