"""Analytics service: aggregated views for dashboard visualizations."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import numpy as np

from ..database import get_pool

logger = logging.getLogger(__name__)

# Shared CTE for workspace access filtering on history_events
_ACCESSIBLE_EVENTS_CTE = """
WITH accessible_events AS (
    SELECT he.id AS event_id
    FROM history_events he
    WHERE he.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
       OR (he.workspace_id IS NULL AND he.created_by = $1)
)
"""

_ACCESSIBLE_NOTEBOOKS_CTE = """
WITH accessible_notebooks AS (
    SELECT n.id AS notebook_id
    FROM notebooks n
    WHERE n.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
       OR (n.workspace_id IS NULL AND n.created_by = $1)
)
"""

_ACCESSIBLE_TABLES_CTE = """
WITH accessible_tables AS (
    SELECT t.id AS table_id
    FROM tables t
    WHERE t.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1)
       OR (t.workspace_id IS NULL AND t.created_by = $1)
)
"""


async def get_activity_timeline(
    user_id: UUID,
    days: int = 30,
    bucket: str = "day",
) -> dict:
    """Agent activity bucketed by time for the timeline visualization."""
    pool = get_pool()
    days = min(days, 90)
    if bucket not in ("hour", "day", "week"):
        bucket = "day"

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await pool.fetch(
        _ACCESSIBLE_EVENTS_CTE + """
        SELECT
            DATE_TRUNC($2, me.created_at) AS bucket_date,
            me.agent_name,
            me.event_type,
            COUNT(*) AS cnt
        FROM history_events me
        JOIN accessible_events a ON a.event_id = me.id
        WHERE me.created_at >= $3
        GROUP BY bucket_date, me.agent_name, me.event_type
        ORDER BY bucket_date
        """,
        user_id, bucket, cutoff,
    )

    # Build response shape
    agents_set: set[str] = set()
    buckets_map: dict[str, dict] = {}

    for row in rows:
        date_str = row["bucket_date"].isoformat()
        agent = row["agent_name"] or "unknown"
        etype = row["event_type"] or "other"
        cnt = row["cnt"]

        agents_set.add(agent)

        if date_str not in buckets_map:
            buckets_map[date_str] = {"date": date_str, "agents": {}}

        b = buckets_map[date_str]
        if agent not in b["agents"]:
            b["agents"][agent] = {"total": 0, "by_type": {}}

        b["agents"][agent]["total"] += cnt
        b["agents"][agent]["by_type"][etype] = (
            b["agents"][agent]["by_type"].get(etype, 0) + cnt
        )

    return {
        "agents": sorted(agents_set),
        "buckets": list(buckets_map.values()),
    }


_density_cache: dict[str, tuple[float, dict]] = {}
_DENSITY_TTL = 300  # 5 minutes

# Common words that survive Postgres stemming but aren't meaningful topics
_STOP_STEMS = frozenset({
    "use", "also", "one", "two", "new", "get", "set", "may", "need",
    "make", "like", "work", "want", "know", "see", "run", "add",
    "way", "tri", "call", "chang", "type", "name", "valu", "file",
    "data", "page", "tabl", "creat", "updat", "delet", "list",
    "function", "return", "true", "false", "null", "string", "number",
    "error", "code", "time", "note", "item", "can", "would", "could",
    "via", "first", "within", "includ", "each", "allow", "provid",
    "ensur", "base", "current", "follow", "implement", "specif",
    "exist", "requir", "support", "differ", "key", "singl", "multi",
    "per", "high", "low", "medium", "fast", "slow", "cost", "date",
    "releas", "window", "context", "speed", "qualiti", "mtok",
    "generat", "check", "result", "build", "process", "issu",
    "perform", "test", "start", "stop", "open", "close", "sourc",
})

import re

# Matches auto-generated column names like col1, col2, column_3, etc.
_COLUMN_NAME_RE = re.compile(r"^col\d+$|^column\d+$|^field\d+$|^row\d+$|^val\d+$")


async def get_knowledge_density(
    user_id: UUID,
    max_clusters: int = 20,
) -> dict:
    """Topic clusters from word frequency for the key topics treemap."""
    pool = get_pool()
    max_clusters = min(max_clusters, 50)

    # Check in-memory cache
    cache_key = f"{user_id}:{max_clusters}"
    now = datetime.now(timezone.utc).timestamp()
    if cache_key in _density_cache:
        cached_at, cached_result = _density_cache[cache_key]
        if now - cached_at < _DENSITY_TTL:
            return cached_result

    # Extract top stems from notebook pages, plus the most common original
    # word that produced each stem so we can display a readable label.
    rows = await pool.fetch(
        _ACCESSIBLE_NOTEBOOKS_CTE + """
        SELECT stem, original_word, ndoc
        FROM (
            SELECT word AS stem,
                   COUNT(DISTINCT np.id) AS ndoc
            FROM notebook_pages np,
                 LATERAL unnest(to_tsvector('english', COALESCE(np.content_markdown, '')))
                     AS t(word, positions, weights)
            WHERE np.notebook_id IN (SELECT notebook_id FROM accessible_notebooks)
              AND np.content_markdown IS NOT NULL
              AND np.content_markdown != ''
              AND length(word) > 2
            GROUP BY word
            ORDER BY ndoc DESC
            LIMIT $2
        ) stems
        CROSS JOIN LATERAL (
            SELECT w AS original_word
            FROM notebook_pages np2,
                 LATERAL regexp_split_to_table(
                     lower(COALESCE(np2.content_markdown, '')), '[^a-z]+'
                 ) AS w
            WHERE np2.notebook_id IN (SELECT notebook_id FROM accessible_notebooks)
              AND to_tsvector('english', w) @@ plainto_tsquery('english', stems.stem)
              AND length(w) > 2
            GROUP BY w
            ORDER BY COUNT(*) DESC
            LIMIT 1
        ) orig
        """,
        user_id, max_clusters * 5,
    )
    page_terms = [(r["stem"], r["original_word"], r["ndoc"]) for r in rows]

    # Same for table rows (stems only, no original-word resolution needed
    # since table data tends to be structured)
    tbl_rows = await pool.fetch(
        _ACCESSIBLE_TABLES_CTE + """
        SELECT word AS stem, COUNT(DISTINCT tr.id) AS ndoc
        FROM table_rows tr,
             LATERAL unnest(to_tsvector('english', COALESCE(tr.data::text, '')))
                 AS t(word, positions, weights)
        WHERE tr.table_id IN (SELECT table_id FROM accessible_tables)
          AND tr.data IS NOT NULL
          AND length(word) > 2
        GROUP BY word
        ORDER BY ndoc DESC
        LIMIT $2
        """,
        user_id, max_clusters * 5,
    )
    table_terms = [(r["stem"], r["ndoc"]) for r in tbl_rows]

    def _is_noise(stem: str) -> bool:
        if stem in _STOP_STEMS:
            return True
        if _COLUMN_NAME_RE.match(stem):
            return True
        if len(stem) <= 3:
            return True
        # Skip pure numbers and numeric-like stems (years, counts)
        if stem.replace(".", "").replace("-", "").isdigit():
            return True
        return False

    # Count total documents for TF-IDF denominator
    total_pages = await pool.fetchval(
        _ACCESSIBLE_NOTEBOOKS_CTE + """
        SELECT COUNT(*) FROM notebook_pages np
        WHERE np.notebook_id IN (SELECT notebook_id FROM accessible_notebooks)
          AND np.content_markdown IS NOT NULL AND np.content_markdown != ''
        """,
        user_id,
    ) or 1
    total_tbl_rows = await pool.fetchval(
        _ACCESSIBLE_TABLES_CTE + """
        SELECT COUNT(*) FROM table_rows tr
        WHERE tr.table_id IN (SELECT table_id FROM accessible_tables)
          AND tr.data IS NOT NULL
        """,
        user_id,
    ) or 1
    total_docs = total_pages + total_tbl_rows

    import math

    # Merge term counts with TF-IDF scoring.
    # IDF = log(total_docs / doc_freq) — down-weights terms that appear everywhere.
    # We use raw doc_freq as the "count" for display sizing, but rank by TF-IDF.
    term_counts: dict[str, dict] = {}
    for stem, original, ndoc in page_terms:
        if _is_noise(stem):
            continue
        term_counts[stem] = {
            "label": original.capitalize(),
            "notebook_pages": ndoc,
            "table_rows": 0,
            "raw_total": ndoc,
        }
    for stem, ndoc in table_terms:
        if _is_noise(stem):
            continue
        if stem in term_counts:
            term_counts[stem]["table_rows"] = ndoc
            term_counts[stem]["raw_total"] += ndoc
        else:
            term_counts[stem] = {
                "label": stem.capitalize(),
                "notebook_pages": 0,
                "table_rows": ndoc,
                "raw_total": ndoc,
            }

    # Compute TF-IDF score for ranking
    for stem, counts in term_counts.items():
        df = counts["raw_total"]
        idf = math.log(total_docs / max(df, 1))
        counts["tfidf"] = df * idf

    # Rank by TF-IDF (surfaces distinctive terms), take top N
    top_terms = sorted(
        term_counts.items(), key=lambda x: x[1]["tfidf"], reverse=True,
    )[:max_clusters]

    if not top_terms:
        result: dict = {"clusters": []}
        _density_cache[cache_key] = (now, result)
        return result

    # Batch enrichment: get sample titles + timestamps for ALL terms in one query
    words = [w for w, _ in top_terms]
    enrichment: dict[str, list[dict]] = {w: [] for w in words}

    enrich_rows = await pool.fetch(
        _ACCESSIBLE_NOTEBOOKS_CTE + """
        SELECT term.word, np.name, np.created_at, np.updated_at
        FROM unnest($2::text[]) AS term(word)
        CROSS JOIN LATERAL (
          SELECT np.name, np.created_at, np.updated_at
          FROM notebook_pages np
          WHERE np.notebook_id IN (SELECT notebook_id FROM accessible_notebooks)
            AND np.content_markdown IS NOT NULL
            AND to_tsvector('english', np.content_markdown) @@ plainto_tsquery('english', term.word)
          ORDER BY np.updated_at DESC
          LIMIT 3
        ) np
        """,
        user_id, words,
    )
    for r in enrich_rows:
        enrichment[r["word"]].append(r)

    # Build clusters — use the resolved original word as label
    clusters = []
    for word, counts in top_terms:
        samples = enrichment.get(word, [])
        newest_at = None
        oldest_at = None
        sample_titles = []
        for s in samples:
            sample_titles.append(s["name"])
            ts = s["updated_at"] or s["created_at"]
            if ts:
                if newest_at is None or ts > newest_at:
                    newest_at = ts
                if oldest_at is None or ts < oldest_at:
                    oldest_at = ts

        clusters.append({
            "label": counts.get("label", word.capitalize()),
            "count": counts["raw_total"],
            "sources": {
                "notebook_pages": counts["notebook_pages"],
                "table_rows": counts["table_rows"],
            },
            "newest_at": newest_at.isoformat() if newest_at else None,
            "oldest_at": oldest_at.isoformat() if oldest_at else None,
            "sample_titles": sample_titles,
        })

    result = {"clusters": clusters}
    _density_cache[cache_key] = (now, result)
    return result


async def get_embedding_projection(
    user_id: UUID,
    max_points: int = 500,
    source: str | None = None,
) -> dict:
    """3D PCA projection of embeddings for the space explorer."""
    pool = get_pool()
    max_points = min(max_points, 2000)

    source_key = source or "_all"

    # Check cache first
    cache = await pool.fetchrow(
        "SELECT points, embedding_count, computed_at FROM embedding_projections "
        "WHERE user_id = $1 AND source_type = $2",
        user_id, source_key,
    )

    # Count current embeddings
    total_count = 0
    if source is None or source == "notebook_pages":
        row = await pool.fetchval(
            _ACCESSIBLE_NOTEBOOKS_CTE + """
            SELECT COUNT(*) FROM notebook_pages np
            WHERE np.notebook_id IN (SELECT notebook_id FROM accessible_notebooks)
              AND np.embedding IS NOT NULL
            """,
            user_id,
        )
        total_count += row or 0

    if source is None or source == "table_rows":
        row = await pool.fetchval(
            _ACCESSIBLE_TABLES_CTE + """
            SELECT COUNT(*) FROM table_rows tr
            WHERE tr.table_id IN (SELECT table_id FROM accessible_tables)
              AND tr.embedding IS NOT NULL
            """,
            user_id,
        )
        total_count += row or 0

    if source is None or source == "history_events":
        row = await pool.fetchval(
            _ACCESSIBLE_EVENTS_CTE + """
            SELECT COUNT(*) FROM history_events me
            JOIN accessible_events a ON a.event_id = me.id
            WHERE me.embedding IS NOT NULL
            """,
            user_id,
        )
        total_count += row or 0

    # Check if cache is still valid
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
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

    # Fetch embeddings from each source
    all_items: list[dict] = []
    per_source_limit = max_points if source else max_points // 3

    if source is None or source == "notebook_pages":
        rows = await pool.fetch(
            _ACCESSIBLE_NOTEBOOKS_CTE + """
            SELECT np.id, np.name AS label, np.embedding, np.created_at
            FROM notebook_pages np
            WHERE np.notebook_id IN (SELECT notebook_id FROM accessible_notebooks)
              AND np.embedding IS NOT NULL
            ORDER BY np.updated_at DESC
            LIMIT $2
            """,
            user_id, per_source_limit,
        )
        for r in rows:
            all_items.append({
                "id": str(r["id"]),
                "label": r["label"],
                "source": "notebook_pages",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "embedding": np.array(r["embedding"]),
            })

    if source is None or source == "table_rows":
        rows = await pool.fetch(
            _ACCESSIBLE_TABLES_CTE + """
            SELECT tr.id, t.name AS table_name, tr.embedding, tr.created_at
            FROM table_rows tr
            JOIN tables t ON t.id = tr.table_id
            WHERE tr.table_id IN (SELECT table_id FROM accessible_tables)
              AND tr.embedding IS NOT NULL
            ORDER BY tr.created_at DESC
            LIMIT $2
            """,
            user_id, per_source_limit,
        )
        for r in rows:
            all_items.append({
                "id": str(r["id"]),
                "label": r["table_name"],
                "source": "table_rows",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "embedding": np.array(r["embedding"]),
            })

    if source is None or source == "history_events":
        rows = await pool.fetch(
            _ACCESSIBLE_EVENTS_CTE + """
            SELECT me.id, me.agent_name, me.event_type, me.embedding, me.created_at
            FROM history_events me
            JOIN accessible_events a ON a.event_id = me.id
            WHERE me.embedding IS NOT NULL
            ORDER BY me.created_at DESC
            LIMIT $2
            """,
            user_id, per_source_limit,
        )
        for r in rows:
            all_items.append({
                "id": str(r["id"]),
                "label": f"{r['agent_name'] or 'agent'}: {r['event_type'] or 'event'}",
                "source": "history_events",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "embedding": np.array(r["embedding"]),
            })

    if not all_items:
        return {"points": [], "stats": {"total_embeddings": total_count, "projected": 0}, "cached": False}

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
        points.append({
            "id": item["id"],
            "x": round(float(coords[i, 0]), 4),
            "y": round(float(coords[i, 1]), 4),
            "z": round(float(coords[i, 2]), 4),
            "source": item["source"],
            "label": item["label"],
            "created_at": item["created_at"],
        })

    # Update cache
    await pool.execute(
        "INSERT INTO embedding_projections (user_id, source_type, points, embedding_count, computed_at) "
        "VALUES ($1, $2, $3, $4, NOW()) "
        "ON CONFLICT (user_id, source_type) "
        "DO UPDATE SET points = $3, embedding_count = $4, computed_at = NOW()",
        user_id, source_key, points, total_count,
    )

    return {
        "points": points,
        "stats": {"total_embeddings": total_count, "projected": len(points)},
        "cached": False,
    }
