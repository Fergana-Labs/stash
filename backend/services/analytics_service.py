"""Analytics service: aggregated views for dashboard visualizations."""

import logging
import math
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np

from ..database import get_pool
from . import memory_service, permission_service

logger = logging.getLogger(__name__)

# Density cache lives in knowledge_density_cache (migration 0017, extended in
# 0018 to include an optional workspace_id so workspace-scoped density reuses
# the same cache table). A precompute worker keeps it warm for active users;
# the endpoint only recomputes inline if the row is missing or the source
# signature drifted. Treat drift as "any source count changed by at least
# SIGNATURE_TOLERANCE" so typo-level edits don't thrash.
_DENSITY_CACHE_TTL = timedelta(hours=24)
_DENSITY_SIGNATURE_TOLERANCE = 0.1


def _truncate_activity_bucket(value: datetime, bucket: str) -> datetime:
    if bucket == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if bucket == "week":
        day = value.replace(hour=0, minute=0, second=0, microsecond=0)
        return day - timedelta(days=day.weekday())
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _activity_bucket_dates(days: int, bucket: str, now: datetime) -> list[datetime]:
    end = _truncate_activity_bucket(now, bucket)
    if bucket == "hour":
        start = end - timedelta(hours=days * 24 - 1)
    elif bucket == "week":
        first_day = _truncate_activity_bucket(now, "day") - timedelta(days=days - 1)
        start = _truncate_activity_bucket(first_day, "week")
    else:
        start = end - timedelta(days=days - 1)

    step = _activity_bucket_step(bucket)
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += step
    return dates


def _activity_bucket_step(bucket: str) -> timedelta:
    if bucket == "hour":
        return timedelta(hours=1)
    if bucket == "week":
        return timedelta(weeks=1)
    return timedelta(days=1)


# Shared CTE for workspace access filtering on history_events.
#   ws_idx -> narrow to a single workspace's events (caller has already
#             authorized membership).
#   None   -> every event the user can see across all their workspaces.
def _accessible_events_cte(
    ws_idx: int | None = None,
    user_idx: int = 1,
) -> str:
    readable_events = memory_service.readable_session_event_condition("he", user_idx)
    if ws_idx is not None:
        return f"""
        WITH accessible_events AS (
            SELECT he.id AS event_id
            FROM history_events he
            WHERE he.workspace_id = ${ws_idx}
              AND {readable_events}
        )
        """
    return f"""
    WITH accessible_events AS (
        SELECT he.id AS event_id
        FROM history_events he
        WHERE (he.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
           OR (he.workspace_id IS NULL AND he.created_by = $1))
          AND (he.workspace_id IS NULL OR {readable_events})
    )
    """


def _accessible_pages_cte(
    ws_idx: int | None = None,
    user_idx: int = 1,
) -> str:
    readable_pages = permission_service.readable_content_condition("page", "p", user_idx)
    if ws_idx is not None:
        return f"""
        WITH accessible_pages AS (
            SELECT p.id AS page_id
            FROM pages p
            WHERE p.workspace_id = ${ws_idx}
              AND {readable_pages}
        )
        """
    return f"""
    WITH accessible_pages AS (
        SELECT p.id AS page_id
        FROM pages p
        WHERE p.workspace_id IN {permission_service.accessible_workspace_ids_sql(1)}
          AND {readable_pages}
    )
    """


def _accessible_tables_cte(
    ws_idx: int | None = None,
    user_idx: int = 1,
) -> str:
    readable_tables = permission_service.readable_content_condition("table", "t", user_idx)
    if ws_idx is not None:
        return f"""
        WITH accessible_tables AS (
            SELECT t.id AS table_id
            FROM tables t
            WHERE t.workspace_id = ${ws_idx}
              AND {readable_tables}
        )
        """
    return f"""
    WITH accessible_tables AS (
        SELECT t.id AS table_id
        FROM tables t
        WHERE (t.workspace_id IN {permission_service.accessible_workspace_ids_sql(1)}
           OR (t.workspace_id IS NULL AND t.created_by = $1))
          AND (t.workspace_id IS NULL OR {readable_tables})
    )
    """


def _accessible_files_cte(
    ws_idx: int | None = None,
    user_idx: int = 1,
) -> str:
    readable_files = permission_service.readable_content_condition("file", "f", user_idx)
    if ws_idx is not None:
        return f"""
        WITH accessible_files AS (
            SELECT f.id AS file_id
            FROM files f
            WHERE f.workspace_id = ${ws_idx}
              AND f.deleted_at IS NULL
              AND {readable_files}
        )
        """
    return f"""
    WITH accessible_files AS (
        SELECT f.id AS file_id
        FROM files f
        WHERE f.workspace_id IN {permission_service.accessible_workspace_ids_sql(1)}
          AND f.deleted_at IS NULL
          AND {readable_files}
    )
    """


async def get_activity_timeline(
    user_id: UUID,
    days: int = 30,
    bucket: str = "day",
    workspace_id: UUID | None = None,
) -> dict:
    """Human + coding-agent session commits bucketed by time.

    Pass ``workspace_id`` to scope to one workspace."""
    pool = get_pool()
    days = min(days, 365)
    if bucket not in ("hour", "day", "week"):
        bucket = "day"

    bucket_dates = _activity_bucket_dates(days, bucket, datetime.now(UTC))
    cutoff = bucket_dates[0]
    end_exclusive = bucket_dates[-1] + _activity_bucket_step(bucket)

    args: list = [user_id, bucket, cutoff, end_exclusive]
    ws_idx = None
    if workspace_id is not None:
        args.append(workspace_id)
        ws_idx = 5

    rows = await pool.fetch(
        _accessible_events_cte(ws_idx=ws_idx) + """
        , timeline_events AS (
            SELECT
                me.workspace_id,
                me.session_id,
                me.created_at,
                me.agent_name,
                me.created_by,
                CASE NULLIF(me.metadata->>'client', '')
                    WHEN 'claude_code' THEN 'claude code'
                    WHEN 'codex_cli' THEN 'codex'
                    WHEN 'gemini_cli' THEN 'gemini'
                    ELSE NULLIF(me.metadata->>'client', '')
                END AS client_name
            FROM history_events me
            JOIN accessible_events a ON a.event_id = me.id
            WHERE me.created_at >= $3
              AND me.created_at < $4
              AND me.session_id IS NOT NULL
        )
        , session_commits AS (
            SELECT
                timeline_events.workspace_id,
                timeline_events.session_id,
                DATE_TRUNC($2, MIN(timeline_events.created_at)) AS bucket_date,
                (
                    ARRAY_AGG(timeline_events.client_name ORDER BY timeline_events.created_at)
                    FILTER (WHERE timeline_events.client_name IS NOT NULL)
                )[1] AS client_name,
                (
                    ARRAY_AGG(timeline_events.agent_name ORDER BY timeline_events.created_at)
                    FILTER (
                        WHERE timeline_events.agent_name IS NOT NULL
                          AND timeline_events.agent_name != ''
                    )
                )[1] AS agent_name,
                (
                    ARRAY_AGG(timeline_events.created_by ORDER BY timeline_events.created_at)
                    FILTER (WHERE timeline_events.created_by IS NOT NULL)
                )[1] AS actor_id
            FROM timeline_events
            GROUP BY timeline_events.workspace_id, timeline_events.session_id
        )
        SELECT
            sc.bucket_date,
            COALESCE(NULLIF(u.display_name, ''), u.name, 'Unknown human') AS human_name,
            COALESCE(
                sc.client_name,
                CASE
                    WHEN sc.agent_name IN ('claude', 'claude-subagent') THEN 'claude code'
                    WHEN sc.agent_name LIKE '%claude-code%' THEN 'claude code'
                    ELSE NULLIF(sc.agent_name, '')
                END,
                'unknown agent'
            ) AS agent_name,
            COUNT(*) AS cnt
        FROM session_commits sc
        LEFT JOIN users u ON u.id = sc.actor_id
        GROUP BY sc.bucket_date, human_name, sc.client_name, sc.agent_name
        ORDER BY bucket_date
        """,
        *args,
    )

    contributors_set: set[str] = set()
    buckets_map: dict[str, dict] = {
        date.isoformat(): {"date": date.isoformat(), "contributors": {}} for date in bucket_dates
    }

    for row in rows:
        date_str = row["bucket_date"].isoformat()
        contributor = f"{row['human_name']} ({row['agent_name']})"
        cnt = row["cnt"]

        contributors_set.add(contributor)

        b = buckets_map[date_str]
        if contributor not in b["contributors"]:
            b["contributors"][contributor] = {"total": 0, "by_type": {}}

        b["contributors"][contributor]["total"] += cnt
        b["contributors"][contributor]["by_type"]["session.commit"] = (
            b["contributors"][contributor]["by_type"].get("session.commit", 0) + cnt
        )

    return {
        "contributors": sorted(contributors_set),
        "buckets": list(buckets_map.values()),
    }


# Common words that survive Postgres stemming but aren't meaningful topics
_STOP_STEMS = frozenset(
    {
        "use",
        "also",
        "one",
        "two",
        "new",
        "get",
        "set",
        "may",
        "need",
        "make",
        "like",
        "work",
        "want",
        "know",
        "see",
        "run",
        "add",
        "way",
        "tri",
        "call",
        "chang",
        "type",
        "name",
        "valu",
        "file",
        "data",
        "page",
        "tabl",
        "creat",
        "updat",
        "delet",
        "list",
        "function",
        "return",
        "true",
        "false",
        "null",
        "string",
        "number",
        "error",
        "code",
        "time",
        "note",
        "item",
        "can",
        "would",
        "could",
        "via",
        "first",
        "within",
        "includ",
        "each",
        "allow",
        "provid",
        "ensur",
        "base",
        "current",
        "follow",
        "implement",
        "specif",
        "exist",
        "requir",
        "support",
        "differ",
        "key",
        "singl",
        "multi",
        "per",
        "high",
        "low",
        "medium",
        "fast",
        "slow",
        "cost",
        "date",
        "releas",
        "window",
        "context",
        "speed",
        "qualiti",
        "mtok",
        "generat",
        "check",
        "result",
        "build",
        "process",
        "issu",
        "perform",
        "test",
        "start",
        "stop",
        "open",
        "close",
        "sourc",
    }
)

# Matches auto-generated column names like col1, col2, column_3, etc.
_COLUMN_NAME_RE = re.compile(r"^col\d+$|^column\d+$|^field\d+$|^row\d+$|^val\d+$")


def _is_noise_stem(stem: str) -> bool:
    if stem in _STOP_STEMS:
        return True
    if _COLUMN_NAME_RE.match(stem):
        return True
    if len(stem) <= 3:
        return True
    if stem.replace(".", "").replace("-", "").isdigit():
        return True
    return False


async def _get_source_counts(user_id: UUID, workspace_id: UUID | None = None) -> dict:
    """Page / row / event counts in one round-trip. Used as both TF-IDF
    denominator and as a cheap fingerprint for cache invalidation."""
    pool = get_pool()
    if workspace_id is not None:
        row = await pool.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM pages p
                 WHERE p.workspace_id = $2
                   AND p.content_markdown IS NOT NULL AND p.content_markdown != ''
                   AND """
            + permission_service.readable_content_condition("page", "p", 1)
            + """) AS pages,
                (SELECT COUNT(*) FROM table_rows tr
                 WHERE tr.table_id IN (
                   SELECT t.id FROM tables t
                   WHERE t.workspace_id = $2
                     AND """
            + permission_service.readable_content_condition("table", "t", 1)
            + """)
                   AND tr.data IS NOT NULL) AS rows,
                (SELECT COUNT(*) FROM history_events he
                 WHERE he.workspace_id = $2
                   AND """
            + memory_service.readable_session_event_condition("he", 1)
            + """) AS events
            """,
            user_id,
            workspace_id,
        )
    else:
        row = await pool.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM pages p
                 WHERE p.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
                   AND p.content_markdown IS NOT NULL AND p.content_markdown != ''
                   AND """
            + permission_service.readable_content_condition("page", "p", 1)
            + """) AS pages,
                (SELECT COUNT(*) FROM table_rows tr
                 WHERE tr.table_id IN (
                     SELECT t.id FROM tables t
                     WHERE (t.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
                        OR (t.workspace_id IS NULL AND t.created_by = $1))
                       AND (t.workspace_id IS NULL OR """
            + permission_service.readable_content_condition("table", "t", 1)
            + """))
                   AND tr.data IS NOT NULL) AS rows,
                (SELECT COUNT(*) FROM history_events he
                 WHERE (he.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
                    OR (he.workspace_id IS NULL AND he.created_by = $1))
                   AND (he.workspace_id IS NULL OR """
            + memory_service.readable_session_event_condition("he", 1)
            + """)) AS events
            """,
            user_id,
        )
    return {"pages": row["pages"], "rows": row["rows"], "events": row["events"]}


async def get_overview_counts(user_id: UUID) -> dict:
    """Counts for the 'Your brain' vitals, spanning the user's own content plus
    everything shared with them. Pages/files run through readable_content_condition
    so a share only surfaces the specific shared rows. Sessions stay member-scoped —
    session sharing isn't reflected in these counts yet."""
    pool = get_pool()
    accessible_ws = permission_service.accessible_workspace_ids_sql(1)
    readable_pages = permission_service.readable_content_condition("page", "p", 1)
    readable_files = permission_service.readable_content_condition("file", "f", 1)
    row = await pool.fetchrow(
        f"""
        SELECT
            (SELECT COUNT(*) FROM pages p
             WHERE p.workspace_id IN {accessible_ws}
               AND p.deleted_at IS NULL
               AND {readable_pages}) AS pages,
            (SELECT COUNT(*) FROM files f
             WHERE f.workspace_id IN {accessible_ws}
               AND f.deleted_at IS NULL
               AND {readable_files}) AS files,
            (SELECT COUNT(*) FROM sessions s
             WHERE s.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
               AND s.deleted_at IS NULL) AS sessions
        """,
        user_id,
    )
    return {"pages": row["pages"], "files": row["files"], "sessions": row["sessions"]}


def _signature(counts: dict) -> int:
    """Pack (pages, rows, events) into a single BIGINT for cheap drift checks."""
    p = min(counts["pages"], 2**20 - 1)
    r = min(counts["rows"], 2**20 - 1)
    e = min(counts["events"], 2**20 - 1)
    return (p << 40) | (r << 20) | e


def _signature_drifted(cached_sig: int, current_counts: dict) -> bool:
    cached_p = (cached_sig >> 40) & (2**20 - 1)
    cached_r = (cached_sig >> 20) & (2**20 - 1)
    cached_e = cached_sig & (2**20 - 1)
    for cached, current in (
        (cached_p, current_counts["pages"]),
        (cached_r, current_counts["rows"]),
        (cached_e, current_counts["events"]),
    ):
        if max(cached, current) == 0:
            continue
        if abs(cached - current) / max(cached, 1) > _DENSITY_SIGNATURE_TOLERANCE:
            return True
    return False


async def compute_knowledge_density(
    user_id: UUID, workspace_id: UUID | None = None
) -> tuple[list[dict], int]:
    """Compute the full top-50 cluster list for a user and return (clusters, signature).

    Single-pass stem aggregation across pages, table rows, and session events
    events. Label prettification is done in Python from one bulk word-frequency
    query — no per-stem LATERAL subqueries."""
    pool = get_pool()
    counts = await _get_source_counts(user_id, workspace_id=workspace_id)
    total_docs = counts["pages"] + counts["rows"] + counts["events"]
    signature = _signature(counts)

    if total_docs == 0:
        return [], signature

    content_args = [user_id]
    content_ws_idx = None
    if workspace_id is not None:
        content_args.append(workspace_id)
        content_ws_idx = 2
    event_args = [user_id]
    event_ws_idx = None
    if workspace_id is not None:
        event_args.append(workspace_id)
        event_ws_idx = 2

    # One scan per source: stem → doc_count + newest_at.
    page_rows = await pool.fetch(
        _accessible_pages_cte(ws_idx=content_ws_idx) + """
        SELECT stem, COUNT(DISTINCT doc_id) AS ndoc, MAX(ts) AS newest_at
        FROM (
            SELECT word AS stem, np.id AS doc_id, np.updated_at AS ts
            FROM pages np,
                 LATERAL unnest(to_tsvector('english', COALESCE(np.content_markdown, '')))
                     AS t(word, positions, weights)
            WHERE np.id IN (SELECT page_id FROM accessible_pages)
              AND np.content_markdown IS NOT NULL AND np.content_markdown != ''
              AND length(word) > 2
        ) x
        GROUP BY stem
        ORDER BY ndoc DESC
        LIMIT 250
        """,
        *content_args,
    )
    table_rows_res = await pool.fetch(
        _accessible_tables_cte(ws_idx=content_ws_idx) + """
        SELECT stem, COUNT(DISTINCT doc_id) AS ndoc, MAX(ts) AS newest_at
        FROM (
            SELECT word AS stem, tr.id AS doc_id, tr.updated_at AS ts
            FROM table_rows tr,
                 LATERAL unnest(to_tsvector('english', COALESCE(tr.data::text, '')))
                     AS t(word, positions, weights)
            WHERE tr.table_id IN (SELECT table_id FROM accessible_tables)
              AND tr.data IS NOT NULL
              AND length(word) > 2
        ) x
        GROUP BY stem
        ORDER BY ndoc DESC
        LIMIT 250
        """,
        *content_args,
    )
    event_rows = await pool.fetch(
        _accessible_events_cte(ws_idx=event_ws_idx) + """
        SELECT stem, COUNT(DISTINCT doc_id) AS ndoc, MAX(ts) AS newest_at
        FROM (
            SELECT word AS stem, he.id AS doc_id, he.created_at AS ts
            FROM history_events he
            JOIN accessible_events a ON a.event_id = he.id,
                 LATERAL unnest(to_tsvector('english', COALESCE(he.content, '')))
                     AS t(word, positions, weights)
            WHERE he.content IS NOT NULL AND he.content != ''
              AND length(word) > 2
        ) x
        GROUP BY stem
        ORDER BY ndoc DESC
        LIMIT 250
        """,
        *event_args,
    )

    term_counts: dict[str, dict] = {}
    for source_rows in (page_rows, table_rows_res, event_rows):
        for r in source_rows:
            stem = r["stem"]
            if _is_noise_stem(stem):
                continue
            bucket = term_counts.setdefault(stem, {"ndoc": 0, "newest_at": None})
            bucket["ndoc"] += r["ndoc"]
            ts = r["newest_at"]
            if ts and (bucket["newest_at"] is None or ts > bucket["newest_at"]):
                bucket["newest_at"] = ts

    if not term_counts:
        return [], signature

    for data in term_counts.values():
        idf = math.log(total_docs / max(data["ndoc"], 1))
        data["tfidf"] = data["ndoc"] * idf

    top_stems = sorted(term_counts.items(), key=lambda x: x[1]["tfidf"], reverse=True)[:50]
    top_stem_set = {stem for stem, _ in top_stems}

    # Pretty labels: one bulk query over pages (the most user-readable
    # source) maps top stems → their most frequent original word. ts_lexize
    # returns the same stems Postgres tsvector produced, so the join is exact.
    word_rows = await pool.fetch(
        _accessible_pages_cte(ws_idx=content_ws_idx) + """
        SELECT w AS word, ts_lexize('english_stem', w) AS stems, COUNT(*) AS freq
        FROM pages np,
             LATERAL regexp_split_to_table(lower(COALESCE(np.content_markdown, '')), '[^a-z]+') AS w
        WHERE np.id IN (SELECT page_id FROM accessible_pages)
          AND length(w) > 3
        GROUP BY w
        ORDER BY freq DESC
        LIMIT 5000
        """,
        *content_args,
    )
    stem_to_label: dict[str, str] = {}
    stem_to_label_freq: dict[str, int] = {}
    for r in word_rows:
        stems = r["stems"] or []
        if not stems:
            continue
        stem = stems[0]
        if stem not in top_stem_set:
            continue
        if r["freq"] > stem_to_label_freq.get(stem, 0):
            stem_to_label[stem] = r["word"]
            stem_to_label_freq[stem] = r["freq"]

    clusters = []
    for stem, data in top_stems:
        label = stem_to_label.get(stem, stem).capitalize()
        clusters.append(
            {
                "label": label,
                "count": data["ndoc"],
                "newest_at": data["newest_at"].isoformat() if data["newest_at"] else None,
            }
        )
    return clusters, signature


async def get_knowledge_density(
    user_id: UUID,
    max_clusters: int = 20,
    workspace_id: UUID | None = None,
) -> dict:
    """Topic clusters for the key topics treemap.

    Reads from knowledge_density_cache (migration 0017/0018) only for explicit
    workspace scopes. User-wide results depend on the user's current workspace
    memberships, so they are recomputed to avoid serving stale customer data
    after offboarding."""
    pool = get_pool()
    max_clusters = min(max_clusters, 50)

    cached = None
    use_cache = workspace_id is not None
    if use_cache:
        cached = await pool.fetchrow(
            "SELECT clusters, source_signature, computed_at FROM knowledge_density_cache "
            "WHERE user_id = $1 AND workspace_id IS NOT DISTINCT FROM $2",
            user_id,
            workspace_id,
        )
    now = datetime.now(UTC)

    if cached and now - cached["computed_at"] < _DENSITY_CACHE_TTL:
        current_counts = await _get_source_counts(user_id, workspace_id=workspace_id)
        if not _signature_drifted(cached["source_signature"], current_counts):
            return {"clusters": cached["clusters"][:max_clusters]}

    clusters, signature = await compute_knowledge_density(user_id, workspace_id=workspace_id)
    if use_cache:
        await pool.execute(
            """
            INSERT INTO knowledge_density_cache (user_id, workspace_id, clusters, source_signature, computed_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (user_id, workspace_id)
            DO UPDATE SET clusters = EXCLUDED.clusters,
                          source_signature = EXCLUDED.source_signature,
                          computed_at = EXCLUDED.computed_at
            """,
            user_id,
            workspace_id,
            clusters,
            signature,
        )
    return {"clusters": clusters[:max_clusters]}


async def get_embedding_projection(
    user_id: UUID,
    max_points: int = 500,
    source: str | None = None,
    workspace_id: UUID | None = None,
) -> dict:
    """3D PCA projection of embeddings for the space explorer.

    Pass ``workspace_id`` to scope to one workspace.

    Only explicit workspace-scoped requests use the embedding_projections cache.
    User-wide results depend on current workspace memberships."""
    pool = get_pool()
    max_points = min(max_points, 2000)

    source_key = source or "_all"

    content_count_args = [user_id]
    content_count_ws_idx = None
    if workspace_id is not None:
        content_count_args.append(workspace_id)
        content_count_ws_idx = 2
    event_count_args = [user_id]
    event_ws_idx = None
    if workspace_id is not None:
        event_count_args.append(workspace_id)
        event_ws_idx = 2

    # Cache row keyed by (user_id, source_type, workspace_id), workspace
    # scopes only: user-wide results depend on the user's current memberships
    # and must be recomputed (offboarding).
    cache = None
    use_cache = workspace_id is not None
    if use_cache:
        cache = await pool.fetchrow(
            "SELECT points, embedding_count, computed_at FROM embedding_projections "
            "WHERE user_id = $1 AND source_type = $2 "
            "AND workspace_id IS NOT DISTINCT FROM $3",
            user_id,
            source_key,
            workspace_id,
        )

    # Count current embeddings
    total_count = 0
    if source is None or source == "pages":
        row = await pool.fetchval(
            _accessible_pages_cte(ws_idx=content_count_ws_idx) + """
            SELECT COUNT(*) FROM pages np
            WHERE np.id IN (SELECT page_id FROM accessible_pages)
              AND np.embedding IS NOT NULL
            """,
            *content_count_args,
        )
        total_count += row or 0

    if source is None or source == "table_rows":
        row = await pool.fetchval(
            _accessible_tables_cte(ws_idx=content_count_ws_idx) + """
            SELECT COUNT(*) FROM table_rows tr
            WHERE tr.table_id IN (SELECT table_id FROM accessible_tables)
              AND tr.embedding IS NOT NULL
            """,
            *content_count_args,
        )
        total_count += row or 0

    if source is None or source == "history_events":
        row = await pool.fetchval(
            _accessible_events_cte(ws_idx=event_ws_idx) + """
            SELECT COUNT(*) FROM history_events me
            JOIN accessible_events a ON a.event_id = me.id
            WHERE me.embedding IS NOT NULL
            """,
            *event_count_args,
        )
        total_count += row or 0

    if source is None or source == "files":
        row = await pool.fetchval(
            _accessible_files_cte(ws_idx=content_count_ws_idx) + """
            SELECT COUNT(*) FROM files f
            WHERE f.id IN (SELECT file_id FROM accessible_files)
              AND f.embedding IS NOT NULL
            """,
            *content_count_args,
        )
        total_count += row or 0

    # Check if cache is still valid
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    if cache and cache["computed_at"] > one_hour_ago:
        count_diff = abs(total_count - cache["embedding_count"])
        if count_diff / max(cache["embedding_count"], 1) < 0.1:
            return {
                "points": cache["points"],
                "stats": {"total_embeddings": total_count, "projected": len(cache["points"])},
                "cached": True,
            }

    if total_count == 0:
        return {"points": [], "stats": {"total_embeddings": 0, "projected": 0}, "cached": False}

    # Fetch embeddings from each source. Divide by the number of sources
    # so the union doesn't exceed max_points by much.
    all_items: list[dict] = []
    per_source_limit = max_points if source else max(max_points // 4, 1)
    content_fetch_args = [user_id, per_source_limit]
    content_fetch_ws_idx = None
    if workspace_id is not None:
        content_fetch_args.append(workspace_id)
        content_fetch_ws_idx = 3
    event_fetch_args = [user_id, per_source_limit]
    event_fetch_ws_idx = None
    if workspace_id is not None:
        event_fetch_args.append(workspace_id)
        event_fetch_ws_idx = 3

    if source is None or source == "pages":
        rows = await pool.fetch(
            _accessible_pages_cte(ws_idx=content_fetch_ws_idx) + """
            SELECT np.id, np.name AS label, np.embedding, np.created_at
            FROM pages np
            WHERE np.id IN (SELECT page_id FROM accessible_pages)
              AND np.embedding IS NOT NULL
            ORDER BY np.updated_at DESC
            LIMIT $2
            """,
            *content_fetch_args,
        )
        for r in rows:
            all_items.append(
                {
                    "id": str(r["id"]),
                    "label": r["label"],
                    "source": "pages",
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "embedding": np.array(r["embedding"]),
                }
            )

    if source is None or source == "table_rows":
        rows = await pool.fetch(
            _accessible_tables_cte(ws_idx=content_fetch_ws_idx) + """
            SELECT tr.id, t.name AS table_name, tr.embedding, tr.created_at
            FROM table_rows tr
            JOIN tables t ON t.id = tr.table_id
            WHERE tr.table_id IN (SELECT table_id FROM accessible_tables)
              AND tr.embedding IS NOT NULL
            ORDER BY tr.created_at DESC
            LIMIT $2
            """,
            *content_fetch_args,
        )
        for r in rows:
            all_items.append(
                {
                    "id": str(r["id"]),
                    "label": r["table_name"],
                    "source": "table_rows",
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "embedding": np.array(r["embedding"]),
                }
            )

    if source is None or source == "history_events":
        rows = await pool.fetch(
            _accessible_events_cte(ws_idx=event_fetch_ws_idx) + """
            SELECT me.id, me.agent_name, me.event_type, me.embedding, me.created_at
            FROM history_events me
            JOIN accessible_events a ON a.event_id = me.id
            WHERE me.embedding IS NOT NULL
            ORDER BY me.created_at DESC
            LIMIT $2
            """,
            *event_fetch_args,
        )
        for r in rows:
            all_items.append(
                {
                    "id": str(r["id"]),
                    "label": f"{r['agent_name'] or 'agent'}: {r['event_type'] or 'event'}",
                    "source": "history_events",
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "embedding": np.array(r["embedding"]),
                }
            )

    if source is None or source == "files":
        rows = await pool.fetch(
            _accessible_files_cte(ws_idx=content_fetch_ws_idx) + """
            SELECT f.id, f.name AS label, f.embedding, f.created_at
            FROM files f
            WHERE f.id IN (SELECT file_id FROM accessible_files)
              AND f.embedding IS NOT NULL
            ORDER BY f.created_at DESC
            LIMIT $2
            """,
            *content_fetch_args,
        )
        for r in rows:
            all_items.append(
                {
                    "id": str(r["id"]),
                    "label": r["label"],
                    "source": "files",
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "embedding": np.array(r["embedding"]),
                }
            )

    if not all_items:
        return {
            "points": [],
            "stats": {"total_embeddings": total_count, "projected": 0},
            "cached": False,
        }

    # 3D PCA projection
    embeddings_matrix = np.stack([item["embedding"] for item in all_items])
    mean = embeddings_matrix.mean(axis=0)
    centered = embeddings_matrix - mean
    if centered.shape[0] > 2:
        cov = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        top3 = eigenvectors[:, -3:][:, ::-1]  # descending by eigenvalue
        coords = centered @ top3
        for dim in range(3):
            mn, mx = coords[:, dim].min(), coords[:, dim].max()
            rng = mx - mn if mx != mn else 1.0
            coords[:, dim] = 2.0 * (coords[:, dim] - mn) / rng - 1.0
    else:
        coords = np.zeros((len(all_items), 3))

    # Build points
    points = []
    for i, item in enumerate(all_items):
        points.append(
            {
                "id": item["id"],
                "x": round(float(coords[i, 0]), 4),
                "y": round(float(coords[i, 1]), 4),
                "z": round(float(coords[i, 2]), 4),
                "source": item["source"],
                "label": item["label"],
                "created_at": item["created_at"],
            }
        )

    if use_cache:
        await pool.execute(
            "INSERT INTO embedding_projections "
            "(user_id, source_type, workspace_id, points, embedding_count, computed_at) "
            "VALUES ($1, $2, $3, $4, $5, NOW()) "
            "ON CONFLICT (user_id, source_type, workspace_id) "
            "DO UPDATE SET points = EXCLUDED.points, "
            "              embedding_count = EXCLUDED.embedding_count, "
            "              computed_at = NOW()",
            user_id,
            source_key,
            workspace_id,
            points,
            total_count,
        )

    return {
        "points": points,
        "stats": {"total_embeddings": total_count, "projected": len(points)},
        "cached": False,
    }
