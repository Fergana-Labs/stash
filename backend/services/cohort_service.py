"""Engagement cohort analysis.

Ports the engagement-only path of github.com/Fergana-Labs/cohort-analysis.
Users are grouped by their first activity, then retention is tracked across
period offsets (months, ISO weeks, or rolling 7-day windows anchored to each
user's first activity).
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from ..database import get_pool

Bucket = str  # "month" | "week" | "rolling_7d"
Mode = str  # "standard" | "future"
EventsFilter = str  # "all" | "active"

_DEFAULT_MAX_PERIOD = {"month": 12, "week": 26, "rolling_7d": 12}
_DEFAULT_COHORT_CAP = {"month": 24, "week": 52, "rolling_7d": 60}


def _bucket_start(ts: datetime, bucket: Bucket) -> datetime:
    """Floor a timestamp to the start of its calendar bucket (UTC)."""
    ts = ts.astimezone(UTC)
    if bucket == "month":
        return datetime(ts.year, ts.month, 1, tzinfo=UTC)
    if bucket == "week":
        d = ts.date() - timedelta(days=ts.weekday())  # Monday
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if bucket == "rolling_7d":
        return datetime(ts.year, ts.month, ts.day, tzinfo=UTC)
    raise ValueError(f"unknown bucket: {bucket}")


def _bucket_label(start: datetime, bucket: Bucket) -> str:
    if bucket == "month":
        return start.strftime("%Y-%m")
    if bucket == "week":
        iso = start.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return start.strftime("%Y-%m-%d")


def _period_offset(cohort_start: datetime, event_start: datetime, bucket: Bucket) -> int:
    """How many bucket-periods after cohort_start does event_start fall in?"""
    if bucket == "month":
        return (event_start.year - cohort_start.year) * 12 + (event_start.month - cohort_start.month)
    if bucket == "week":
        return (event_start.date() - cohort_start.date()).days // 7
    if bucket == "rolling_7d":
        return (event_start.date() - cohort_start.date()).days // 7
    raise ValueError(f"unknown bucket: {bucket}")


def compute_engagement_cohorts(
    rows: list[dict],
    bucket: Bucket = "month",
    mode: Mode = "standard",
    max_period: int | None = None,
) -> dict:
    """Compute cohort retention from raw (user_id, signup_at, event_at) rows.

    Rows are pre-sorted by user_id, event_at ASC. event_at may be None for
    users with no events — they're placed in their signup cohort with zero
    activity.
    """
    if bucket not in _DEFAULT_MAX_PERIOD:
        raise ValueError(f"unknown bucket: {bucket}")
    if mode not in ("standard", "future"):
        raise ValueError(f"unknown mode: {mode}")
    if max_period is None:
        max_period = _DEFAULT_MAX_PERIOD[bucket]

    user_cohort: dict[str, datetime] = {}
    user_active_periods: dict[str, set[int]] = defaultdict(set)
    user_event_counts_by_period: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    by_user: dict[str, list[dict]] = defaultdict(list)
    signup_at: dict[str, datetime] = {}
    for r in rows:
        uid = str(r["id"])
        signup_at[uid] = r["signup_at"]
        if r["event_at"] is not None:
            by_user[uid].append(r)

    for uid, signup in signup_at.items():
        events = by_user.get(uid, [])
        anchor = events[0]["event_at"] if events else signup
        user_cohort[uid] = _bucket_start(anchor, bucket)

    for uid, events in by_user.items():
        cohort_start = user_cohort[uid]
        for e in events:
            event_start = _bucket_start(e["event_at"], bucket)
            p = _period_offset(cohort_start, event_start, bucket)
            if p < 0 or p > max_period:
                continue
            user_active_periods[uid].add(p)
            user_event_counts_by_period[uid][p] += 1

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
                active = sum(1 for u in uids if p in user_active_periods[u])
            else:
                active = sum(1 for u in uids if any(q >= p for q in user_active_periods[u]))
            retention.append(active / size if size else 0.0)
            active_users.append(active)
            period_actions = sum(user_event_counts_by_period[u].get(p, 0) for u in uids)
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
    total_events = sum(
        sum(counts.values()) for counts in user_event_counts_by_period.values()
    )

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
    "(he.metadata->>'client') IS NULL "
    "AND COALESCE(he.metadata->>'source', '') <> 'history_import'"
)


async def get_engagement_cohorts(
    bucket: Bucket = "month",
    mode: Mode = "standard",
    max_period: int | None = None,
    events_filter: EventsFilter = "all",
) -> dict:
    if events_filter not in ("all", "active"):
        raise ValueError(f"unknown events_filter: {events_filter}")
    pool = get_pool()
    join_filter = f"AND {_ACTIVE_EVENTS_PREDICATE}" if events_filter == "active" else ""
    sql = f"""
        SELECT u.id, u.created_at AS signup_at,
               he.created_at AS event_at
        FROM users u
        LEFT JOIN history_events he
            ON he.created_by = u.id
            {join_filter}
        ORDER BY u.id, he.created_at NULLS FIRST
    """
    rows = await pool.fetch(sql)
    out = compute_engagement_cohorts(
        [dict(r) for r in rows],
        bucket=bucket,
        mode=mode,
        max_period=max_period,
    )
    out["events_filter"] = events_filter
    return out
