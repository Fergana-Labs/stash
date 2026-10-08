"""Step labels and rule-based step scores: the automatic annotation of a trace.

A labeling model says what each step is: what the user is doing, how they
reacted to which answer, what a tool call did and returned, and what the agent
handed the user (step_labeler). Fixed rules then turn the labels into a score
per step, with credit passed back from answers the user reacted to, and a
score per task (step_scoring).

The workbench runs this for every recorded trace version (workbench_auto) and
stores the outcome as that version's evaluation. The labels and the score
breakdown live in rm_step_labels and are merged into each step's
`metadata.label` and `metadata.reward` when the trace is read, the same place
an import can put them. A trace that arrives already labeled is never sent to
a model.

Trace content is sent to the labeling provider, and to the grading model for
quality checks when TYPESAFE_API_KEY is set. Long traces use overlapping context
windows; oversized messages are explicitly excerpted without skipping steps.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from uuid import UUID

import httpx

from ...config import settings
from ...database import get_pool
from . import step_context, step_labeler, step_scoring

logger = logging.getLogger(__name__)

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# The grading model reads about 32k tokens of state; long tool results are clipped to fit.
JEV_STATE_CHARS = 84_000
CONCURRENCY = 8


NOT_CONFIGURED = "OPENAI_API_KEY is not configured; automatic annotation cannot label this trace."


class LabelingSkipped(Exception):
    """Annotation cannot run, for example without a provider key or agent steps."""


def fingerprint(steps: list[dict]) -> str:
    digest = hashlib.sha256()
    for step in steps:
        digest.update(
            json.dumps(
                [
                    step["idx"],
                    step["role"],
                    step["content"],
                    step["tool_name"],
                    step["tool_call_id"],
                ]
            ).encode()
        )
    return digest.hexdigest()


def check_state(chunks: list[dict], target: dict, label: dict) -> dict:
    index = next(i for i, chunk in enumerate(chunks) if chunk["chunk_id"] == target["chunk_id"])
    context = step_context.window(chunks, index, index + 1, 80)
    step = step_labeler.clip(step_labeler.render_chunk(target, 8_000), 16_000)
    conversation = step_context.render(
        context, JEV_STATE_CHARS - len(step) - 2_000, partial=len(context) < len(chunks)
    )
    described = (label["type"] or "other").replace("_", " ")
    if label["is_output"]:
        described = f"response to the user; outcome: {label['outcome']}; stance: {label['stance']}; coverage: {label['coverage']}"
    elif label["type"] == "tool_call":
        described = f"tool call to {label.get('tool')}; effect: {label['effect']}; result: {label['result'] or 'none recorded'}"
    return {"CONVERSATION": conversation, "STEP_TO_JUDGE": step, "STEP_LABEL": described}


async def quality_check(
    client: httpx.AsyncClient, chunks: list[dict], chunk: dict, label: dict, rubric: str
) -> dict:
    """The grading model's answer to one step's quality check, as level probabilities."""
    question, levels = step_scoring.CHECKS[rubric]
    body = {
        "model": settings.JEV_MODEL,
        "state": check_state(chunks, chunk, label),
        "questions": {
            "grade": {
                "type": "score",
                "instructions": question,
                "criteria": [text for text, _, _ in levels],
            }
        },
    }
    try:
        response = await client.post(
            JEV_ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {settings.TYPESAFE_API_KEY}"},
        )
    except httpx.RequestError as exc:
        raise step_labeler.LabelingError(
            f"quality check request failed: {type(exc).__name__}"
        ) from exc
    if response.status_code != 200:
        raise step_labeler.LabelingError(
            f"quality check returned {response.status_code}: {response.text[:200]}"
        )
    try:
        raw = response.json()["answers"]["grade"]["probabilities"]
        probabilities = {int(level): float(p) for level, p in raw.items()}
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise step_labeler.LabelingError(
            "quality check response was not the expected JSON"
        ) from exc
    return {"rubric": rubric, "grader": "the grading model", "probabilities": probabilities}


async def score_steps(chunks: list[dict], labels: dict[str, dict]) -> tuple[dict[str, dict], dict]:
    """Scores for the labeled agent chunks, keyed by step index, and the task
    scores. Quality checks are asked only when the grading model is
    configured; without it the labels' fixed points stand."""
    verdicts = {
        label["verdict_target"]: label["verdict"]
        for label in labels.values()
        if label["actor"] == "user"
        and label["verdict"] not in (None, "none")
        and label["verdict_target"]
    }
    agent_steps = [
        {"chunk_id": c["chunk_id"], "task_id": labels[c["chunk_id"]]["task_id"], "label": labels[c["chunk_id"]],
         "verdict": verdicts.get(c["chunk_id"]), "check": None, "chunk": c}
        for c in chunks if c["actor"] == "agent"
    ]  # fmt: skip
    if settings.TYPESAFE_API_KEY:
        gate = asyncio.Semaphore(CONCURRENCY)
        async with httpx.AsyncClient(timeout=settings.JEV_TIMEOUT_SECONDS) as client:

            async def check(step: dict) -> None:
                rubric = step_scoring.check_for(step["label"], step["verdict"])
                if rubric is not None:
                    async with gate:
                        step["check"] = await quality_check(
                            client, chunks, step["chunk"], step["label"], rubric
                        )

            await asyncio.gather(*(check(step) for step in agent_steps))
    rewards, episodes = step_scoring.score_trace(agent_steps)
    by_idx = {c["chunk_id"]: str(c["idx"]) for c in chunks}
    return {
        by_idx[chunk_id]: reward for chunk_id, reward in rewards.items()
    }, step_scoring.summarize(list(labels.values()), episodes)


def chunk_hash(chunk: dict) -> str:
    return hashlib.sha256(json.dumps(chunk, sort_keys=True, default=str).encode()).hexdigest()


async def label_steps(
    trace_id: UUID, chunks: list[dict], reuse: dict[str, dict]
) -> dict[str, dict]:
    """A label per chunk. `reuse` holds labels from the trace's previous version
    for chunks that have not changed, so appended work costs only its own calls."""
    labels = {c["chunk_id"]: reuse[c["chunk_id"]] for c in chunks if c["chunk_id"] in reuse}
    todo = [c for c in chunks if c["chunk_id"] not in labels]
    if todo and not settings.OPENAI_API_KEY:
        raise LabelingSkipped(NOT_CONFIGURED)
    gate = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=180) as client:

        for targets, transcript in step_context.batches(
            chunks, settings.STEP_LABELING_MAX_CHUNKS, settings.STEP_LABELING_MAX_CHARS
        ):
            pending = [chunk for chunk in targets if chunk["chunk_id"] not in labels]
            if not pending:
                continue
            cache_key = f"{trace_id}:{hashlib.sha256(transcript.encode()).hexdigest()[:16]}"

            async def label(chunk: dict) -> None:
                async with gate:
                    labels[chunk["chunk_id"]] = await step_labeler.label_chunk(
                        client, cache_key, transcript, chunk
                    )

            # Warm this window's cached prefix, then label its remaining targets.
            await label(pending[0])
            await asyncio.gather(*(label(chunk) for chunk in pending[1:]))
    step_labeler.assign_tasks(chunks, labels)
    return labels


def imported(trace: dict, steps: list[dict], chunks: list[dict]) -> dict | None:
    """The labels and scores a trace arrived with, or None when it has none."""
    labels = {
        str(step["idx"]): step["metadata"]["label"]
        for step in steps
        if isinstance((step.get("metadata") or {}).get("label"), dict)
    }
    if not labels:
        return None
    rewards = {
        str(step["idx"]): step["metadata"]["reward"]
        for step in steps
        if isinstance((step.get("metadata") or {}).get("reward"), dict)
    }
    return {
        "labels": labels,
        "rewards": rewards,
        "summary": (trace.get("metadata") or {}).get("rubric_summary"),
        "by_chunk": {
            c["chunk_id"]: labels[str(c["idx"])] for c in chunks if str(c["idx"]) in labels
        },
    }


async def annotate(trace: dict, steps: list[dict]) -> dict:
    """Labels, step scores and task scores for one trace version, each keyed by
    step index. Labels the trace arrived with are used as they are; otherwise
    the stored result is reused when the steps have not changed, and only new
    or changed steps are sent to the labeling model. Raises LabelingSkipped or
    LabelingError."""
    pool = get_pool()
    chunks = step_labeler.build_chunks(steps)
    if not any(chunk["actor"] == "agent" for chunk in chunks):
        raise LabelingSkipped("The trace has no agent steps to annotate.")
    given = imported(trace, steps, chunks)
    if given is not None:
        if not given["rewards"] and len(given["by_chunk"]) == len(chunks):
            given["rewards"], given["summary"] = await score_steps(chunks, given["by_chunk"])
        return given
    current = fingerprint(steps)
    previous = await pool.fetchrow(
        "SELECT fingerprint, labels, rewards, summary, chunks FROM rm_step_labels WHERE trace_id = $1",
        trace["id"],
    )
    if previous is not None and previous["fingerprint"] == current:
        return {key: previous[key] for key in ("labels", "rewards", "summary")}
    hashes = {c["chunk_id"]: chunk_hash(c) for c in chunks}
    reuse = {}
    if previous is not None:
        by_idx = {c["chunk_id"]: str(c["idx"]) for c in chunks}
        reuse = {
            chunk_id: previous["labels"][by_idx[chunk_id]]
            for chunk_id, digest in hashes.items()
            if previous["chunks"].get(chunk_id) == digest and by_idx[chunk_id] in previous["labels"]
        }
    by_chunk = await label_steps(trace["id"], chunks, reuse)
    rewards, summary = await score_steps(chunks, by_chunk)
    labels = {str(chunk["idx"]): by_chunk[chunk["chunk_id"]] for chunk in chunks}
    await pool.execute(
        """
        INSERT INTO rm_step_labels
          (trace_id, owner_user_id, fingerprint, labels, rewards, summary, chunks, label_model)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (trace_id) DO UPDATE SET
          fingerprint = EXCLUDED.fingerprint, labels = EXCLUDED.labels, rewards = EXCLUDED.rewards,
          summary = EXCLUDED.summary, chunks = EXCLUDED.chunks, label_model = EXCLUDED.label_model,
          labeled_at = now()
        """,
        trace["id"], trace["owner_user_id"], current, labels, rewards, summary, hashes,
        settings.STEP_LABEL_MODEL,
    )  # fmt: skip
    return {"labels": labels, "rewards": rewards, "summary": summary}


async def merge_into(trace_id: UUID, detail: dict) -> dict:
    """Attach stored labels and scores to a trace detail's steps as
    `metadata.label` and `metadata.reward`, and the task scores as
    `step_scores`: the shape an imported trace already carries (imported
    values win)."""
    given = (detail.get("metadata") or {}).get("rubric_summary")
    if given is not None:
        detail["step_scores"] = given
    row = await get_pool().fetchrow(
        "SELECT labels, rewards, summary FROM rm_step_labels WHERE trace_id = $1", trace_id
    )
    if row is None:
        return detail
    for step in detail["steps"]:
        key = str(step["index"])
        extra = {
            name: row[field][key]
            for name, field in (("label", "labels"), ("reward", "rewards"))
            if key in row[field]
        }
        if extra:
            step["metadata"] = {**extra, **(step["metadata"] or {})}
    detail.setdefault("step_scores", row["summary"])
    return detail
