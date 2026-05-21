"""Aggregations powering the /admin/analytics dashboard.

Two source tables:
  - analytics_events (lightweight product telemetry: onboarding, web actions, stash CLI)
  - history_events (agent-transcript log; we slice it by metadata->>'client')

Everything here is admin-gated upstream — no per-user permission checks.
"""

from datetime import UTC, datetime, timedelta

from ..database import get_pool

# Canonical funnel order. Reads top-of-funnel → bottom; missing steps render
# as gaps so dashboards can show drop-off honestly.
ONBOARDING_FUNNEL_STAGES: list[tuple[str, str]] = [
    ("viewed", "onboarding.viewed"),
    ("path_selected", "onboarding.path_selected"),
    ("step_viewed", "onboarding.step_viewed"),
    ("completed", "onboarding.completed"),
]


async def get_onboarding_funnel(*, days: int = 30, path: str | None = None) -> dict:
    """Distinct-user counts per stage in the canonical onboarding order.

    A user 'enters' a stage if they emitted *any* event of that name in the
    window. step_viewed compresses every step into one bucket because
    individual step counts come from path-mix; the funnel is meant to read
    at a glance.
    """
    pool = get_pool()
    since = datetime.now(UTC) - timedelta(days=days)
    path_filter = ""
    args: list = [since]
    if path:
        path_filter = "AND (properties->>'path' = $2 OR event_name = 'onboarding.viewed')"
        args.append(path)

    sql = f"""
        SELECT event_name, COUNT(DISTINCT user_id) AS users
        FROM analytics_events
        WHERE created_at >= $1
          AND event_name = ANY($%d::text[])
          {path_filter}
        GROUP BY event_name
    """ % (len(args) + 1)
    args.append([name for _, name in ONBOARDING_FUNNEL_STAGES])

    rows = await pool.fetch(sql, *args)
    counts = {r["event_name"]: r["users"] for r in rows}

    stages = []
    prev: int | None = None
    for label, event_name in ONBOARDING_FUNNEL_STAGES:
        users = int(counts.get(event_name, 0))
        drop_off = None if prev is None or prev == 0 else (prev - users) / prev
        stages.append(
            {
                "stage": label,
                "event_name": event_name,
                "users": users,
                "drop_off_pct": drop_off,
            }
        )
        prev = users

    return {
        "days": days,
        "path": path,
        "stages": stages,
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def get_path_mix(*, days: int = 30, bucket: str = "day") -> dict:
    """Daily/weekly counts of onboarding.path_selected, grouped by path."""
    if bucket not in ("day", "week"):
        raise ValueError(f"unknown bucket: {bucket}")
    trunc = "day" if bucket == "day" else "week"
    pool = get_pool()
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await pool.fetch(
        f"""
        SELECT date_trunc('{trunc}', created_at) AS ts,
               properties->>'path' AS path,
               COUNT(*) AS n
        FROM analytics_events
        WHERE event_name = 'onboarding.path_selected'
          AND created_at >= $1
        GROUP BY 1, 2
        ORDER BY 1 ASC
        """,
        since,
    )
    return {
        "days": days,
        "bucket": bucket,
        "rows": [
            {"ts": r["ts"].isoformat(), "path": r["path"], "count": int(r["n"])} for r in rows
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def get_surface_mix(*, days: int = 30, bucket: str = "day") -> dict:
    """Daily activity by surface across both tables.

    Surfaces we expose:
      - web: analytics_events.surface = 'web'
      - cli (stash): analytics_events.surface = 'cli'
      - cli (plugin: <client>): history_events.metadata->>'client' for each plugin
    """
    if bucket not in ("day", "week"):
        raise ValueError(f"unknown bucket: {bucket}")
    trunc = "day" if bucket == "day" else "week"
    pool = get_pool()
    since = datetime.now(UTC) - timedelta(days=days)

    rows = await pool.fetch(
        f"""
        WITH ae AS (
            SELECT date_trunc('{trunc}', created_at) AS ts,
                   CASE
                       WHEN surface = 'web' THEN 'web'
                       WHEN surface = 'cli' THEN 'cli:stash'
                       ELSE 'other'
                   END AS surface_key,
                   COUNT(*) AS n
            FROM analytics_events
            WHERE created_at >= $1
            GROUP BY 1, 2
        ),
        he AS (
            SELECT date_trunc('{trunc}', created_at) AS ts,
                   'plugin:' || COALESCE(metadata->>'client', 'unknown') AS surface_key,
                   COUNT(*) AS n
            FROM history_events
            WHERE created_at >= $1
              AND metadata->>'client' IS NOT NULL
              AND COALESCE(metadata->>'source', '') <> 'history_import'
            GROUP BY 1, 2
        )
        SELECT * FROM ae
        UNION ALL
        SELECT * FROM he
        ORDER BY ts ASC
        """,
        since,
    )

    return {
        "days": days,
        "bucket": bucket,
        "rows": [
            {"ts": r["ts"].isoformat(), "surface": r["surface_key"], "count": int(r["n"])}
            for r in rows
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def get_top_events(*, days: int = 30, limit: int = 20) -> dict:
    """Most-frequent event names in analytics_events over the window."""
    pool = get_pool()
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await pool.fetch(
        """
        SELECT event_name,
               COUNT(*) AS total,
               COUNT(DISTINCT user_id) AS users
        FROM analytics_events
        WHERE created_at >= $1
        GROUP BY event_name
        ORDER BY total DESC
        LIMIT $2
        """,
        since,
        limit,
    )
    return {
        "days": days,
        "rows": [
            {
                "event_name": r["event_name"],
                "total": int(r["total"]),
                "users": int(r["users"]),
            }
            for r in rows
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def get_summary(*, days: int = 7) -> dict:
    """Top-of-dashboard stat boxes: signups, completions, active users, CLI installs."""
    pool = get_pool()
    since = datetime.now(UTC) - timedelta(days=days)

    signups = await pool.fetchval("SELECT COUNT(*) FROM users WHERE created_at >= $1", since)
    completed = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT user_id) FROM analytics_events
        WHERE event_name = 'onboarding.completed' AND created_at >= $1
        """,
        since,
    )
    # Distinct users who ran *any* stash CLI command in the window. Better
    # signal than just `install` because there's no install command — `connect`
    # is the canonical first-run, but a user invoking `share` or `upload`
    # is just as much an active CLI user.
    cli_active = await pool.fetchval(
        """
        SELECT COUNT(DISTINCT user_id) FROM analytics_events
        WHERE event_name = 'cli.command_invoked' AND created_at >= $1
        """,
        since,
    )
    # Active users = distinct user_id across analytics_events + non-plugin
    # history_events. Plugin events are firehose and would dominate.
    active_users = await pool.fetchval(
        """
        SELECT COUNT(*) FROM (
            SELECT user_id FROM analytics_events
            WHERE user_id IS NOT NULL AND created_at >= $1
            UNION
            SELECT created_by AS user_id FROM history_events
            WHERE created_by IS NOT NULL
              AND created_at >= $1
              AND (metadata->>'client') IS NULL
              AND COALESCE(metadata->>'source', '') <> 'history_import'
        ) u
        """,
        since,
    )

    return {
        "days": days,
        "signups": int(signups or 0),
        "onboardings_completed": int(completed or 0),
        "active_users": int(active_users or 0),
        "cli_active_users": int(cli_active or 0),
        "generated_at": datetime.now(UTC).isoformat(),
    }
