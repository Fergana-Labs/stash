"""Automatic step labels for traces.

Once a trace has been quiet for a few minutes, a labeling model says what each
step is: what the user is doing, how they reacted to which answer, what a tool
call did and returned, and what the agent handed the user (step_labeler). The
automatic annotation in the workbench estimates how well a step went; these
labels are the observable facts next to that number.

Labels live in rm_step_labels and are merged into each step's
`metadata.label` when the trace is read, the same place an import can put
them, so the trace view shows both the same way.

Off unless STEP_LABELING_ENABLED is set. Trace content is sent to the labeling
provider; traces above the size limits are skipped, never truncated silently.
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
from . import step_labeler

logger = logging.getLogger(__name__)

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


async def label_steps(trace_id: UUID, steps: list[dict]) -> dict[str, dict]:
    """Labels for one trace's steps, keyed by step index. Raises
    LabelingSkipped or LabelingError; makes no database writes."""
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
    return {str(chunk["idx"]): labels[chunk["chunk_id"]] for chunk in chunks}


def configured() -> bool:
    return bool(settings.STEP_LABELING_ENABLED and settings.OPENAI_API_KEY)


async def label_trace(trace_id: UUID) -> str:
    """Label one trace if its steps changed since the last time. Returns the outcome."""
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

    status, error, labels = "succeeded", None, {}
    try:
        labels = await label_steps(trace_id, steps)
    except LabelingSkipped as skipped:
        status, error = "skipped", str(skipped)
    except step_labeler.LabelingError as failed:
        logger.warning(
            "step labeling failed trace=%s attempt=%s error=%s", trace_id, attempts, failed
        )
        status, error = "failed", str(failed)[:500]
    await pool.execute(
        """
        INSERT INTO rm_step_labels (trace_id, owner_user_id, fingerprint, status, error, attempts, labels, label_model)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (trace_id) DO UPDATE SET
          fingerprint = EXCLUDED.fingerprint, status = EXCLUDED.status, error = EXCLUDED.error,
          attempts = EXCLUDED.attempts, labels = EXCLUDED.labels, label_model = EXCLUDED.label_model,
          labeled_at = now(), checked_at = now()
        """,
        trace_id, owner, current, status, error, attempts, labels, settings.STEP_LABEL_MODEL,
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
    """Attach stored labels to a trace detail's steps as `metadata.label`, the
    shape an imported trace already carries (imported labels win), and report
    a labeling run that has not produced labels."""
    row = await get_pool().fetchrow(
        "SELECT status, error, labels FROM rm_step_labels WHERE trace_id = $1", trace_id
    )
    if row is None:
        return detail
    if row["status"] != "succeeded":
        detail["step_labeling"] = {"status": row["status"], "error": row["error"]}
        return detail
    for step in detail["steps"]:
        label = row["labels"].get(str(step["index"]))
        if label is not None:
            step["metadata"] = {"label": label, **(step["metadata"] or {})}
    return detail
