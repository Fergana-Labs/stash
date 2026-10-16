"""Trends: how often each behavior happens, per day, and how that is moving.

A count alone rises with traffic, so each day also carries the rate: the share
of that day's scanned traces with at least one hit. Days are the day the trace
was recorded, so a backfill lands where the behavior actually happened.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from ...database import get_pool


def _days(n: int) -> list[date]:
    today = datetime.now(UTC).date()
    return [today - timedelta(days=i) for i in range(n - 1, -1, -1)]


async def overview(owner_id: UUID, days: int = 30) -> dict:
    pool = get_pool()
    behaviors = await pool.fetch(
        "SELECT * FROM behaviors WHERE owner_user_id = $1 ORDER BY actor, name", owner_id
    )
    hits = await pool.fetch(
        """SELECT h.behavior_id, (t.created_at AT TIME ZONE 'UTC')::date AS day,
                  count(*)::int AS hits, count(DISTINCT h.trace_id)::int AS traces
           FROM behavior_hits h JOIN rm_traces t ON t.id = h.trace_id
           WHERE h.owner_user_id = $1 AND t.created_at > now() - make_interval(days => $2)
             AND h.review IS DISTINCT FROM 'rejected'
           GROUP BY 1, 2""",
        owner_id,
        days,
    )
    scanned = await pool.fetch(
        """SELECT sc.behavior_id, (t.created_at AT TIME ZONE 'UTC')::date AS day, count(*)::int AS traces
           FROM behavior_scans sc JOIN rm_traces t ON t.id = sc.trace_id
           JOIN behaviors b ON b.id = sc.behavior_id
           WHERE b.owner_user_id = $1 AND t.created_at > now() - make_interval(days => $2)
           GROUP BY 1, 2""",
        owner_id,
        days,
    )
    counts = {(r["behavior_id"], r["day"]): r for r in hits}
    denominators = {(r["behavior_id"], r["day"]): r["traces"] for r in scanned}
    axis = _days(days)
    out = []
    for b in behaviors:
        series = []
        for day in axis:
            row = counts.get((b["id"], day))
            total = denominators.get((b["id"], day), 0)
            with_hit = row["traces"] if row else 0
            series.append(
                {
                    "day": day.isoformat(),
                    "hits": row["hits"] if row else 0,
                    "traces_with_hit": with_hit,
                    "traces_scanned": total,
                    "rate": (with_hit / total) if total else None,
                }
            )
        week, prior = series[-7:], series[-14:-7]
        this_week, last_week = sum(d["hits"] for d in week), sum(d["hits"] for d in prior)
        out.append(
            {
                "behavior": _public(b),
                "series": series,
                "last_7_days": this_week,
                "previous_7_days": last_week,
                "change": None if last_week == 0 else (this_week - last_week) / last_week,
                "traces_scanned": sum(d["traces_scanned"] for d in series),
            }
        )
    return {"days": days, "behaviors": out}


def _public(row) -> dict:
    keep = (
        "id", "name", "slug", "actor", "definition", "examples", "detector", "rule", "severity",
        "enabled", "alert", "last_alert_at", "eval_id", "version", "created_at", "updated_at",
    )  # fmt: skip
    return {k: row[k] for k in keep}
