"""Engagement cohort analysis.

Ports the engagement-only path of github.com/Fergana-Labs/cohort-analysis.
Users are grouped by their first activity, then retention is tracked across
period offsets (months, ISO weeks, or rolling 7-day windows anchored to each
user's first activity).

The heavy lifting happens in SQL: Postgres reduces the raw event stream to
one row per user × active period, so the rows crossing the wire scale with
user count, not event count. Python only pivots those aggregates into the
retention matrix.
"""

from collections import defaultdict
from datetime import UTC, datetime

from ..database import get_pool
from .admin_analytics_service import internal_filter_sql

Bucket = str  # "month" | "week" | "rolling_7d"
Mode = str  # "standard" | "future"
EventsFilter = str  # "all" | "active"

_DEFAULT_MAX_PERIOD = {"month": 12, "week": 26, "rolling_7d": 12}
_DEFAULT_COHORT_CAP = {"month": 24, "week": 52, "rolling_7d": 60}


def _bucket_sql(bucket: Bucket) -> tuple[str, str]:
    """SQL for (cohort start over min(event_utc), period offset of one event).

    Both expressions work on naive-UTC timestamps (event_at AT TIME ZONE
    'UTC'), matching the UTC flooring the retention math is defined in.
    `ue` is an event row, `c` carries the user's cohort_start.
    """
    if bucket == "month":
        return (
            "date_trunc('month', min(event_utc))",
            "(EXTRACT(YEAR FROM ue.event_utc)::int * 12 + EXTRACT(MONTH FROM ue.event_utc)::int)"
            " - (EXTRACT(YEAR FROM c.cohort_start)::int * 12"
            " + EXTRACT(MONTH FROM c.cohort_start)::int)",
        )
    if bucket == "week":
        # date_trunc('week') floors to the ISO Monday. The cohort start is a
        # Monday, so integer-dividing the day gap by 7 lands each event in
        # its calendar week without flooring the event separately.
        return (
            "date_trunc('week', min(event_utc))",
            "(ue.event_utc::date - c.cohort_start::date) / 7",
        )
    if bucket == "rolling_7d":
        return (
            "date_trunc('day', min(event_utc))",
            "(ue.event_utc::date - c.cohort_start::date) / 7",
        )
    raise ValueError(f"unknown bucket: {bucket}")


def _bucket_label(start: datetime, bucket: Bucket) -> str:
    if bucket == "month":
        return start.strftime("%Y-%m")
    # week: render the Monday date so users can read the actual week
    # without translating ISO week numbers in their head.
    return start.strftime("%Y-%m-%d")


def compute_engagement_cohorts(
    rows: list[dict],
    bucket: Bucket = "month",
    mode: Mode = "standard",
    max_period: int | None = None,
) -> dict:
    """Pivot per-user period aggregates into the retention matrix.

    Each row is one user × active period: {user_id, cohort_start, period,
    events}, with periods already limited to [0, max_period]. Users with no
    events have no rows and belong to no cohort — including them would leave
    all-zero rows in the denominator and pull period-0 retention below 100%.
    """
    if bucket not in _DEFAULT_MAX_PERIOD:
        raise ValueError(f"unknown bucket: {bucket}")
    if mode not in ("standard", "future"):
        raise ValueError(f"unknown mode: {mode}")
    if max_period is None:
        max_period = _DEFAULT_MAX_PERIOD[bucket]

    user_cohort: dict[str, datetime] = {}
    user_period_counts: dict[str, dict[int, int]] = defaultdict(dict)
    for r in rows:
        uid = str(r["user_id"])
        user_cohort[uid] = r["cohort_start"]
        user_period_counts[uid][int(r["period"])] = int(r["events"])

    cohort_users: dict[datetime, list[str]] = defaultdict(list)
    for uid, cs in user_cohort.items():
        cohort_users[cs].append(uid)

    cohorts_out = []
    for cs in sorted(cohort_users.keys(), reverse=True):
        uids = cohort_users[cs]
        size = len(uids)
        retention = []
        active_users = []
        actions = []
        avg_cum_actions = []
        running_cum_total = 0
        for p in range(max_period + 1):
            if mode == "standard":
                active = sum(1 for u in uids if p in user_period_counts[u])
            else:
                active = sum(1 for u in uids if any(q >= p for q in user_period_counts[u]))
            retention.append(active / size if size else 0.0)
            active_users.append(active)
            period_actions = sum(user_period_counts[u].get(p, 0) for u in uids)
            actions.append(period_actions)
            running_cum_total += period_actions
            avg_cum_actions.append(running_cum_total / size if size else 0.0)

        cohorts_out.append(
            {
                "cohort_label": _bucket_label(cs, bucket),
                "cohort_start": cs.isoformat(),
                "size": size,
                "retention": retention,
                "active_users": active_users,
                "actions": actions,
                "avg_cumulative_actions": avg_cum_actions,
            }
        )

    cap = _DEFAULT_COHORT_CAP[bucket]
    cohorts_out = cohorts_out[:cap]

    total_users = sum(c["size"] for c in cohorts_out)
    total_events = sum(sum(counts.values()) for counts in user_period_counts.values())

    return {
        "bucket": bucket,
        "mode": mode,
        "max_period": max_period,
        "cohorts": cohorts_out,
        "totals": {"users": total_users, "events": total_events},
        "generated_at": datetime.now(UTC).isoformat(),
    }


# Hook events from the Claude Code / Cursor / etc. plugins all set
# metadata.client (e.g. "claude_code"); imported sessions set
# metadata.source = "history_import". "Active" events are the rest —
# CLI commands and any custom-typed events.
_ACTIVE_EVENTS_PREDICATE = (
    "(he.metadata->>'client') IS NULL AND COALESCE(he.metadata->>'source', '') <> 'history_import'"
)


async def get_engagement_cohorts(
    bucket: Bucket = "month",
    mode: Mode = "standard",
    max_period: int | None = None,
    events_filter: EventsFilter = "all",
    exclude_internal: bool = True,
) -> dict:
    if events_filter not in ("all", "active"):
        raise ValueError(f"unknown events_filter: {events_filter}")
    cohort_start_sql, period_sql = _bucket_sql(bucket)
    if max_period is None:
        max_period = _DEFAULT_MAX_PERIOD[bucket]
    pool = get_pool()
    # Pull from both event tables. history_events is the agent-transcript log;
    # analytics_events is product telemetry. UNION ALL lets web-only users
    # (who never trigger an agent session) show up in cohorts.
    he_filter = f"AND {_ACTIVE_EVENTS_PREDICATE}" if events_filter == "active" else ""
    sql = f"""
        WITH user_events AS (
            SELECT he.created_by AS user_id,
                   he.created_at AT TIME ZONE 'UTC' AS event_utc
            FROM history_events he
            WHERE he.created_by IS NOT NULL
              {he_filter}
            UNION ALL
            SELECT ae.user_id, ae.created_at AT TIME ZONE 'UTC'
            FROM analytics_events ae
            WHERE ae.user_id IS NOT NULL
        ),
        cohort_starts AS (
            SELECT user_id, {cohort_start_sql} AS cohort_start
            FROM user_events
            WHERE {internal_filter_sql("user_events.user_id", exclude_internal)}
            GROUP BY user_id
        )
        SELECT c.user_id,
               c.cohort_start,
               {period_sql} AS period,
               COUNT(*) AS events
        FROM user_events ue
        JOIN cohort_starts c ON c.user_id = ue.user_id
        WHERE {period_sql} <= $1
        GROUP BY 1, 2, 3
    """
    rows = await pool.fetch(sql, max_period)
    # date_trunc over a naive-UTC timestamp comes back naive; re-attach UTC so
    # cohort_start serializes with an offset, as the API always has.
    out = compute_engagement_cohorts(
        [
            {
                "user_id": r["user_id"],
                "cohort_start": r["cohort_start"].replace(tzinfo=UTC),
                "period": r["period"],
                "events": r["events"],
            }
            for r in rows
        ],
        bucket=bucket,
        mode=mode,
        max_period=max_period,
    )
    out["events_filter"] = events_filter
    return out
