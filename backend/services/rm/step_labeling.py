"""Automatic step labels for traces.

Once a trace has been quiet for a few minutes, a labeling model says what each
step is: what the user is doing, how they reacted to which answer, what a tool
call did and returned, and what the agent handed the user (step_labeler). The
automatic annotation in the workbench estimates how well a step went; these
labels are the observable facts next to that number.

Each labeled step then gets a rule-based score with credit assignment
(step_scoring): fixed points for its label, one quality check, and a share of
any later answer the user reacted to.

Labels and scores live in rm_step_labels and are merged into each step's
`metadata.label` and `metadata.reward` when the trace is read, the same place
an import can put them, so the trace view shows both the same way.

Off unless STEP_LABELING_ENABLED is set. Trace content is sent to the labeling
provider, and to the grading model for quality checks when TYPESAFE_API_KEY is
set; traces above the size limits are skipped, never truncated silently.
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
from . import step_labeler, step_scoring

logger = logging.getLogger(__name__)

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# The grading model reads about 32k tokens of state; long tool results are clipped to fit.
JEV_STATE_CHARS = 84_000
JEV_RESULT_CAPS = (8_000, 3_000, 1_200, 400)
CONCURRENCY = 8
MAX_ATTEMPTS = 3
TRACES_PER_PASS = 5
QUIET_MINUTES = 5


class LabelingSkipped(Exception):
    """The trace is outside what automatic labeling handles; the reason is user-facing."""


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
    for cap in JEV_RESULT_CAPS:
        conversation = step_labeler.render(chunks, cap)
        step = step_labeler.render_chunk(target, max(cap, 6_000))
        if len(conversation) + len(step) <= JEV_STATE_CHARS:
            break
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


async def label_steps(trace_id: UUID, steps: list[dict]) -> dict:
    """Labels and scores for one trace's steps, keyed by step index, plus the
    task scores. Raises LabelingSkipped or LabelingError; makes no database writes."""
    chunks = step_labeler.build_chunks(steps)
    if not any(chunk["actor"] == "agent" for chunk in chunks):
        raise LabelingSkipped("The trace has no agent steps to label.")
    if len(chunks) > settings.STEP_LABELING_MAX_CHUNKS:
        raise LabelingSkipped(
            f"The trace has {len(chunks)} steps; automatic labeling handles up to {settings.STEP_LABELING_MAX_CHUNKS}."
        )
    transcript = step_labeler.render(chunks)
    if len(transcript) > settings.STEP_LABELING_MAX_CHARS:
        raise LabelingSkipped(
            f"The trace is {len(transcript):,} characters; automatic labeling handles up to {settings.STEP_LABELING_MAX_CHARS:,}."
        )

    gate = asyncio.Semaphore(CONCURRENCY)
    labels: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=180) as client:

        async def label(chunk: dict) -> None:
            async with gate:
                labels[chunk["chunk_id"]] = await step_labeler.label_chunk(
                    client, str(trace_id), transcript, chunk
                )

        # The first call writes the shared prompt prefix to the provider's cache; the rest read it.
        await label(chunks[0])
        await asyncio.gather(*(label(chunk) for chunk in chunks[1:]))
    step_labeler.assign_tasks(chunks, labels)
    rewards, summary = await score_steps(chunks, labels)
    return {
        "labels": {str(chunk["idx"]): labels[chunk["chunk_id"]] for chunk in chunks},
        "rewards": rewards,
        "summary": summary,
    }


def configured() -> bool:
    return bool(settings.STEP_LABELING_ENABLED and settings.OPENAI_API_KEY)


async def label_trace(trace_id: UUID) -> str:
    """Label and score one trace if its steps changed since the last time. Returns the outcome."""
    pool = get_pool()
    owner = await pool.fetchval("SELECT owner_user_id FROM rm_traces WHERE id = $1", trace_id)
    if owner is None:
        return "gone"
    steps = [
        dict(row)
        for row in await pool.fetch(
            "SELECT * FROM rm_trace_steps WHERE trace_id = $1 ORDER BY idx", trace_id
        )
    ]
    current = fingerprint(steps)
    previous = await pool.fetchrow(
        "SELECT fingerprint, status, attempts FROM rm_step_labels WHERE trace_id = $1", trace_id
    )
    same = previous is not None and previous["fingerprint"] == current
    if same and (
        previous["status"] not in ("failed", "pending") or previous["attempts"] >= MAX_ATTEMPTS
    ):
        await pool.execute(
            "UPDATE rm_step_labels SET checked_at = now() WHERE trace_id = $1", trace_id
        )
        return "unchanged"
    attempts = previous["attempts"] + 1 if same else 1

    status, error, result = "succeeded", None, {"labels": {}, "rewards": {}, "summary": None}
    try:
        result = await label_steps(trace_id, steps)
    except LabelingSkipped as skipped:
        status, error = "skipped", str(skipped)
    except step_labeler.LabelingError as failed:
        logger.warning(
            "step labeling failed trace=%s attempt=%s error=%s", trace_id, attempts, failed
        )
        status, error = "failed", str(failed)[:500]
    await pool.execute(
        """
        INSERT INTO rm_step_labels
          (trace_id, owner_user_id, fingerprint, status, error, attempts, labels, rewards, summary, label_model)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (trace_id) DO UPDATE SET
          fingerprint = EXCLUDED.fingerprint, status = EXCLUDED.status, error = EXCLUDED.error,
          attempts = EXCLUDED.attempts, labels = EXCLUDED.labels, rewards = EXCLUDED.rewards,
          summary = EXCLUDED.summary, label_model = EXCLUDED.label_model,
          labeled_at = now(), checked_at = now()
        """,
        trace_id, owner, current, status, error, attempts,
        result["labels"], result["rewards"], result["summary"], settings.STEP_LABEL_MODEL,
    )  # fmt: skip
    return status


async def claim_due() -> list[UUID]:
    """Claim a few traces to label: new or changed, quiet for QUIET_MINUTES,
    owned by an account with reward models, and not already carrying imported
    labels. A claim is a `pending` row, so the next sweep does not pick the
    same trace again; a claim nobody finished is released after half an hour."""
    if not configured():
        return []
    rows = await get_pool().fetch(
        f"""
        INSERT INTO rm_step_labels (trace_id, owner_user_id, fingerprint, status, label_model)
        SELECT t.id, t.owner_user_id, '', 'pending', $1 FROM rm_traces t
        JOIN users u ON u.id = t.owner_user_id AND u.reward_models_enabled
        LEFT JOIN rm_step_labels g ON g.trace_id = t.id
        WHERE t.updated_at < now() - interval '{QUIET_MINUTES} minutes'
          AND NOT EXISTS (SELECT 1 FROM rm_trace_steps s WHERE s.trace_id = t.id AND s.metadata ? 'label')
          AND (g.trace_id IS NULL OR g.checked_at < t.updated_at
               OR (g.status = 'pending' AND g.checked_at < now() - interval '30 minutes')
               OR (g.status = 'failed' AND g.attempts < {MAX_ATTEMPTS} AND g.checked_at < now() - interval '10 minutes'))
        ORDER BY t.updated_at DESC
        LIMIT {TRACES_PER_PASS}
        ON CONFLICT (trace_id) DO UPDATE SET checked_at = now()
        RETURNING trace_id
        """,
        settings.STEP_LABEL_MODEL,
    )
    return [row["trace_id"] for row in rows]


async def merge_into(trace_id: UUID, detail: dict) -> dict:
    """Attach stored labels and scores to a trace detail's steps as
    `metadata.label` and `metadata.reward`, and the task scores as
    `step_scores`: the shape an imported trace already carries (imported
    values win). Reports a labeling run that has not produced labels."""
    imported = (detail.get("metadata") or {}).get("rubric_summary")
    if imported is not None:
        detail["step_scores"] = imported
    row = await get_pool().fetchrow(
        "SELECT status, error, labels, rewards, summary FROM rm_step_labels WHERE trace_id = $1",
        trace_id,
    )
    if row is None:
        return detail
    if row["status"] != "succeeded":
        detail["step_labeling"] = {"status": row["status"], "error": row["error"]}
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
