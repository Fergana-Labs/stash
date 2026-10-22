"""Task types: what each trace was asked to do, so cohorts can split by task.

Each trace's first user request is embedded; the requests are clustered and
Claude names each cluster in a few words ("refund requests", "bug fixes").
New traces join the nearest named cluster without a model call; the whole set
is reclustered when there are many unassigned traces or none are named yet.
"""

from __future__ import annotations

import math
from uuid import UUID

import numpy as np
from pydantic import BaseModel, Field

from ...database import get_pool
from .. import embeddings, llm

REQUEST_CHARS = 600
MAX_TRACES = 1_500
RECLUSTER_SHARE = 0.25


class _Names(BaseModel):
    names: list[str] = Field(
        description="One short task name (2-4 words, lowercase) per cluster, in order"
    )


async def _requests(owner_id: UUID, days: int) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT t.id, tt.task_type,
                  (SELECT left(content, $3) FROM rm_trace_steps s WHERE s.trace_id = t.id AND s.role = 'user'
                   ORDER BY s.idx LIMIT 1) AS request
           FROM rm_traces t LEFT JOIN rm_trace_task_types tt ON tt.trace_id = t.id
           WHERE t.owner_user_id = $1 AND t.created_at > now() - make_interval(days => $2)
           ORDER BY t.created_at DESC LIMIT $4""",
        owner_id, days, REQUEST_CHARS, MAX_TRACES,
    )  # fmt: skip
    return [dict(r) for r in rows if r["request"]]


async def _name(groups: list[list[str]]) -> list[str]:
    listing = "\n\n".join(
        f"CLUSTER {i}:\n" + "\n".join(f"- {r[:200]}" for r in g[:8]) for i, g in enumerate(groups)
    )
    result = await llm.complete_structured(
        prompt=listing,
        system="Name what kind of task each cluster of user requests to an AI agent is, in 2-4 lowercase words (for example 'refund requests', 'bug fixes', 'order tracking'). Names must be distinct.",
        output_model=_Names,
        tier=llm.ModelTier.FAST,
        max_tokens=500,
    )
    names = [n.strip().lower()[:60] or f"tasks {i + 1}" for i, n in enumerate(result.names)]
    return (names + [f"tasks {i + 1}" for i in range(len(names), len(groups))])[: len(groups)]


async def refresh(owner_id: UUID, days: int = 30) -> int:
    """Assign task types to traces that have none; returns how many were assigned."""
    from ..intuition.curation import kmeans

    rows = await _requests(owner_id, days)
    todo = [r for r in rows if r["task_type"] is None]
    if not todo or not embeddings.is_configured():
        return 0
    named = [r for r in rows if r["task_type"] is not None]
    recluster = not named or len(todo) > RECLUSTER_SHARE * len(rows)
    targets = rows if recluster else todo
    vecs = await embeddings.embed_batch([r["request"] for r in targets])
    if not vecs:
        return 0
    X = np.array([v / (np.linalg.norm(v) or 1.0) for v in vecs])
    if recluster:
        k = max(1, min(8, len(targets) // 3, round(math.sqrt(len(targets)))))
        assign = kmeans(X, k) if k > 1 else np.zeros(len(targets), dtype=int)
        groups = [
            [targets[i]["request"] for i in range(len(targets)) if assign[i] == c] for c in range(k)
        ]
        names = await _name(groups)
        labels = [names[assign[i]] for i in range(len(targets))]
    else:
        known = await embeddings.embed_batch([r["request"] for r in named])
        K = np.array([v / (np.linalg.norm(v) or 1.0) for v in known])
        nearest = (X @ K.T).argmax(axis=1)
        labels = [named[j]["task_type"] for j in nearest]
    await get_pool().executemany(
        """INSERT INTO rm_trace_task_types (trace_id, owner_user_id, task_type) VALUES ($1, $2, $3)
           ON CONFLICT (trace_id) DO UPDATE SET task_type = EXCLUDED.task_type, assigned_at = now()""",
        [(r["id"], owner_id, label) for r, label in zip(targets, labels)],
    )
    return len(targets)
