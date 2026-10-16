"""Release markers: did a behavior get better or worse when the agent changed?

A release is a point in time (optionally for one agent) where the prompt,
model, tools or code changed. Comparing a behavior's rate in the traces
before and after it is the test the behaviors post describes: "run tests to
check whether a change improved new rollouts". Rates come with Wilson
intervals and a two-proportion z-test, so a move on a handful of traces is
not called a win.
"""

from __future__ import annotations

import math
from datetime import datetime
from uuid import UUID

from ...database import get_pool
from ..rm.monitoring import AGENT_SQL

DEFAULT_WINDOW_DAYS = 7


class NotFound(LookupError):
    pass


async def create(
    owner_id: UUID, label: str, agent: str | None, released_at: datetime | None, note: str
) -> dict:
    row = await get_pool().fetchrow(
        """INSERT INTO agent_releases (owner_user_id, agent, label, note, released_at)
           VALUES ($1, $2, $3, $4, coalesce($5, now())) RETURNING id, agent, label, note, released_at""",
        owner_id, agent or None, label, note, released_at,
    )  # fmt: skip
    return dict(row)


async def list_releases(owner_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, agent, label, note, released_at FROM agent_releases WHERE owner_user_id = $1 ORDER BY released_at DESC",
        owner_id,
    )
    return [dict(r) for r in rows]


async def delete(owner_id: UUID, release_id: UUID) -> None:
    status = await get_pool().execute(
        "DELETE FROM agent_releases WHERE id = $1 AND owner_user_id = $2", release_id, owner_id
    )
    if status.endswith(" 0"):
        raise NotFound("Release not found")


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0.0, centre - half), min(1.0, centre + half)]


def significant(k1: int, n1: int, k2: int, n2: int) -> bool:
    """Two-proportion z-test at the 5% level."""
    if not n1 or not n2:
        return False
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    return se > 0 and abs(k1 / n1 - k2 / n2) / se > 1.96


async def _side(behavior_id: UUID, owner_id: UUID, agent, start, end) -> dict:
    row = await get_pool().fetchrow(
        f"""SELECT count(*)::int AS traces,
                   count(*) FILTER (WHERE EXISTS (
                     SELECT 1 FROM behavior_hits h WHERE h.trace_id = t.id AND h.behavior_id = $1
                     AND h.review IS DISTINCT FROM 'rejected'))::int AS with_hit
            FROM behavior_scans sc JOIN rm_traces t ON t.id = sc.trace_id
            WHERE sc.behavior_id = $1 AND t.owner_user_id = $2
              AND t.created_at >= $4 AND t.created_at < $5
              AND ($3::text IS NULL OR {AGENT_SQL} = $3)""",
        behavior_id, owner_id, agent, start, end,
    )  # fmt: skip
    n, k = row["traces"], row["with_hit"]
    return {"traces": n, "with_hit": k, "rate": (k / n) if n else None, "ci": wilson(k, n)}


async def compare(
    owner_id: UUID, behavior_id: UUID, release_id: UUID, window_days: int = DEFAULT_WINDOW_DAYS
) -> dict:
    from datetime import timedelta

    release = await get_pool().fetchrow(
        "SELECT id, agent, label, note, released_at FROM agent_releases WHERE id = $1 AND owner_user_id = $2",
        release_id,
        owner_id,
    )
    if release is None:
        raise NotFound("Release not found")
    at, span = release["released_at"], timedelta(days=window_days)
    before = await _side(behavior_id, owner_id, release["agent"], at - span, at)
    after = await _side(behavior_id, owner_id, release["agent"], at, at + span)
    change = (
        None if before["rate"] is None or after["rate"] is None else after["rate"] - before["rate"]
    )
    return {
        "release": dict(release),
        "before": before,
        "after": after,
        "change": change,
        "significant": significant(
            before["with_hit"], before["traces"], after["with_hit"], after["traces"]
        ),
        "window_days": window_days,
    }
