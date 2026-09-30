"""Training data built from annotations: preference pairs, score items, GEPA examples.

These rules are the contract in docs/reward-models/DESIGN.md ("Reward model
training" and "Skill creation (GEPA)"). Annotations flagged with
`label_error` never reach any of them: a label someone marked as wrong must
not teach the reward model or steer GEPA.
"""

import json
import random
from uuid import UUID

from ...database import get_pool

DEFAULT_MAX_PAIRS = 4000
# The worker holds out at least one pair for eval, so it needs one more to train on.
MIN_PAIRS = 2


class NotEnoughPairs(ValueError):
    pass


def check_enough_pairs(pairs: list[dict]) -> None:
    if len(pairs) < MIN_PAIRS:
        raise NotEnoughPairs(
            f"the selected traces have {len(pairs)} preference pairs; need at least "
            f"{MIN_PAIRS}. Automatic assessment could not establish enough grounded comparisons. "
            "Include more completed conversations with task context and assistant responses."
        )


async def all_trace_ids(owner_user_id: UUID) -> list[UUID]:
    rows = await get_pool().fetch(
        "SELECT id FROM rm_traces WHERE owner_user_id = $1 ORDER BY id", owner_user_id
    )
    return [row["id"] for row in rows]


def render_step(step: dict) -> str:
    if step["role"] == "assistant" and step["tool_name"]:
        call = f"assistant → {step['tool_name']}({json.dumps(step['tool_input'])})"
        if not step["content"]:
            return call
        return f"assistant: {step['content']}\n{call}"
    return f"{step['role']}: {step['content']}"


def render_steps(steps: list[dict]) -> str:
    # GEPA's skill is injected into the system message; a reward model that saw it could be gamed.
    return "\n\n".join(render_step(step) for step in steps if step["role"] != "system")


async def _steps_by_trace(owner_user_id: UUID) -> dict[UUID, list[dict]]:
    rows = await get_pool().fetch(
        """
        SELECT s.trace_id, s.idx, s.role, s.content, s.tool_name, s.tool_input
        FROM rm_trace_steps s
        JOIN rm_traces t ON t.id = s.trace_id
        WHERE t.owner_user_id = $1
        ORDER BY s.trace_id, s.idx
        """,
        owner_user_id,
    )
    grouped: dict[UUID, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["trace_id"], []).append(dict(row))
    return grouped


async def build_pairs(
    owner_user_id: UUID, trace_ids: list[UUID], max_pairs: int = DEFAULT_MAX_PAIRS
) -> list[dict]:
    """Every (chosen, rejected) combination within a granularity, seeded shuffle, capped.

    Only annotations on `trace_ids` count; ids that no longer exist add nothing.
    """
    targets = await get_pool().fetch(
        """
        SELECT a.trace_id, s.idx AS step_idx, SUM(a.rating)::int AS total
        FROM rm_annotations a
        LEFT JOIN rm_trace_steps s ON s.id = a.step_id
        WHERE a.owner_user_id = $1 AND a.trace_id = ANY($2::uuid[])
          AND a.rating IS NOT NULL AND NOT a.label_error
        GROUP BY a.trace_id, a.step_id, s.idx
        ORDER BY a.trace_id, s.idx NULLS FIRST
        """,
        owner_user_id,
        trace_ids,
    )
    steps_by_trace = await _steps_by_trace(owner_user_id)

    chosen: dict[str, list[str]] = {"trace": [], "step": []}
    rejected: dict[str, list[str]] = {"trace": [], "step": []}
    for target in targets:
        if target["total"] == 0:
            continue
        steps = steps_by_trace[target["trace_id"]]
        if target["step_idx"] is None:
            level = "trace"
            text = render_steps(steps)
        else:
            level = "step"
            text = render_steps([s for s in steps if s["idx"] <= target["step_idx"]])
        bucket = chosen if target["total"] > 0 else rejected
        bucket[level].append(text)

    pairs = [
        {"chosen": good, "rejected": bad}
        for level in ("trace", "step")
        for good in chosen[level]
        for bad in rejected[level]
    ]
    random.Random(0).shuffle(pairs)
    return pairs[:max_pairs]


async def score_items(owner_user_id: UUID) -> list[dict]:
    """Every trace the owner has, rendered whole, for scoring after training."""
    steps_by_trace = await _steps_by_trace(owner_user_id)
    return [
        {"trace_id": str(trace_id), "text": render_steps(steps)}
        for trace_id, steps in steps_by_trace.items()
    ]


async def gepa_examples(owner_user_id: UUID, trace_ids: list[UUID]) -> list[dict]:
    """Selected traces among `trace_ids` as GEPA inputs: the conversation before
    the first assistant turn.

    The trace's own system prompt travels separately (`system`) because the
    worker appends the candidate skill to it. A trace with no non-system step
    before its first assistant step has no input to replay, so it cannot be an
    example.
    """
    selected = await get_pool().fetch(
        """
        SELECT
          t.id AS trace_id,
          COALESCE(
            array_agg(a.comment ORDER BY a.created_at) FILTER (WHERE a.comment IS NOT NULL),
            '{}'
          ) AS comments
        FROM rm_traces t
        LEFT JOIN rm_annotations a ON a.trace_id = t.id AND NOT a.label_error
        WHERE t.owner_user_id = $1 AND t.id = ANY($2::uuid[])
        GROUP BY t.id
        ORDER BY t.id
        """,
        owner_user_id,
        trace_ids,
    )
    steps_by_trace = await _steps_by_trace(owner_user_id)

    examples = []
    for row in selected:
        steps = steps_by_trace[row["trace_id"]]
        system_parts = [step["content"] for step in steps if step["role"] == "system"]
        messages = []
        for step in steps:
            if step["role"] == "assistant":
                break
            if step["role"] == "system":
                continue
            messages.append({"role": step["role"], "content": step["content"]})
        if not messages:
            continue
        examples.append(
            {
                "trace_id": str(row["trace_id"]),
                "system": "\n\n".join(system_parts) if system_parts else None,
                "messages": messages,
                "feedback": row["comments"],
            }
        )
    return examples
