"""Cohorts: production traces bucketed by how they went, to see where the agent is consistent.

Each trace gets a few facts from data it already has: its agent, how many tool
calls it made, how the user reacted (corrections, repeats and negative
messages from the step labels), how it ended (the last answer's outcome), and
which behaviors it showed. Grouping by one of those shows which slices of real
usage fail, and each cohort's traces are where implicit preferences get mined
into eval criteria (intuition/mining.py).
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from ...database import get_pool
from ..rm.monitoring import AGENT_SQL

DIMENSIONS = ("agent", "outcome", "satisfaction", "behavior", "tool_use", "task_type")
MAX_TRACES = 2_000
SAMPLE = 5


def facts(labels: dict | None, tool_calls: int) -> dict:
    """Satisfaction and outcome of one trace from its step labels."""
    ordered = [labels[k] for k in sorted(labels or {}, key=int)]
    users = [label for label in ordered if label.get("actor") == "user"]
    corrections = sum(label.get("intent") in ("correction", "repeat_request") for label in users)
    negative = sum(label.get("sentiment") == "negative" for label in users)
    verdicts = [
        label.get("verdict") for label in users if label.get("verdict") not in (None, "none")
    ]
    outputs = [label for label in ordered if label.get("is_output")]
    if labels is None:
        satisfaction = "unlabeled"
    elif corrections or negative:
        satisfaction = "frustrated"
    elif verdicts and verdicts[-1] in ("confirmed", "implicit_positive"):
        satisfaction = "satisfied"
    else:
        satisfaction = "no signal"
    if tool_calls == 0:
        tool_use = "no tools"
    elif tool_calls <= 5:
        tool_use = "1–5 tool calls"
    elif tool_calls <= 20:
        tool_use = "6–20 tool calls"
    else:
        tool_use = "20+ tool calls"
    return {
        "corrections": corrections,
        "negative": negative,
        "satisfaction": satisfaction,
        "outcome": (outputs[-1].get("outcome") or "unknown")
        if outputs
        else ("unlabeled" if labels is None else "no answer"),
        "tool_use": tool_use,
    }


async def traces(owner_id: UUID, days: int) -> list[dict]:
    rows = await get_pool().fetch(
        f"""SELECT t.id, t.title, t.created_at, {AGENT_SQL} AS agent, l.labels,
                   coalesce(tt.task_type, 'unclassified') AS task_type,
                   (SELECT count(*) FROM rm_trace_steps s WHERE s.trace_id = t.id AND s.tool_name IS NOT NULL)::int AS tool_calls,
                   coalesce((SELECT array_agg(DISTINCT b.name) FROM behavior_hits h JOIN behaviors b ON b.id = h.behavior_id
                             WHERE h.trace_id = t.id AND h.review IS DISTINCT FROM 'rejected'), '{{}}') AS behaviors
            FROM rm_traces t LEFT JOIN rm_step_labels l ON l.trace_id = t.id
            LEFT JOIN rm_trace_task_types tt ON tt.trace_id = t.id
            WHERE t.owner_user_id = $1 AND t.created_at > now() - make_interval(days => $2)
            ORDER BY t.created_at DESC LIMIT $3""",
        owner_id,
        days,
        MAX_TRACES,
    )
    return [{**dict(r), **facts(r["labels"], r["tool_calls"])} for r in rows]


def keys(trace: dict, by: str) -> list[str]:
    if by == "behavior":
        return list(trace["behaviors"]) or ["no behaviors"]
    return [str(trace[by])]


async def overview(owner_id: UUID, by: str = "outcome", days: int = 30) -> dict:
    if by not in DIMENSIONS:
        raise ValueError(f"Group by one of {', '.join(DIMENSIONS)}")
    if by == "task_type":
        from . import task_types

        await task_types.refresh(owner_id, days)
    all_traces = await traces(owner_id, days)
    groups: dict[str, list[dict]] = {}
    for t in all_traces:
        for key in keys(t, by):
            groups.setdefault(key, []).append(t)
    total = len(all_traces) or 1
    cohorts = []
    for key, members in groups.items():
        n = len(members)
        behaviors = Counter(b for t in members for b in t["behaviors"])
        cohorts.append(
            {
                "key": key,
                "traces": n,
                "share": n / total,
                "frustrated_rate": sum(t["satisfaction"] == "frustrated" for t in members) / n,
                "correction_rate": sum(t["corrections"] > 0 for t in members) / n,
                "avg_tool_calls": sum(t["tool_calls"] for t in members) / n,
                "outcomes": dict(Counter(t["outcome"] for t in members)),
                "top_behaviors": behaviors.most_common(5),
                "sample": [{"trace_id": t["id"], "title": t["title"]} for t in members[:SAMPLE]],
            }
        )
    cohorts.sort(key=lambda c: -c["traces"])
    return {"by": by, "days": days, "traces": len(all_traces), "cohorts": cohorts}


async def members(owner_id: UUID, by: str, key: str, days: int) -> list[dict]:
    if by not in DIMENSIONS:
        raise ValueError(f"Group by one of {', '.join(DIMENSIONS)}")
    return [t for t in await traces(owner_id, days) if key in keys(t, by)]
