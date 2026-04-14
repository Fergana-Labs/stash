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
})


async def get_knowledge_density(
    user_id: UUID,
    max_clusters: int = 20,
) -> dict:
    """Topic clusters from FTS term extraction for the density heatmap."""
    pool = get_pool()
    max_clusters = min(max_clusters, 50)

    # Check in-memory cache
    cache_key = f"{user_id}:{max_clusters}"
    now = datetime.now(timezone.utc).timestamp()
    if cache_key in _density_cache:
        cached_at, cached_result = _density_cache[cache_key]
        if now - cached_at < _DENSITY_TTL:
            return cached_result

    # Get accessible notebook IDs first, then build ts_stat query
    nb_ids = await pool.fetch(
        "SELECT n.id FROM notebooks n "
        "WHERE n.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1) "
        "   OR (n.workspace_id IS NULL AND n.created_by = $1)",
        user_id,
    )
    nb_id_list = [str(r["id"]) for r in nb_ids]

    page_terms: list = []
    if nb_id_list:
        # ts_stat requires a literal SQL string — build it with escaped UUIDs
        ids_literal = ",".join(f"'{uid}'" for uid in nb_id_list)
        page_terms = await pool.fetch(
            f"SELECT word, ndoc, nentry "
            f"FROM ts_stat("
            f"  'SELECT to_tsvector(''english'', np.content_markdown) "
            f"   FROM notebook_pages np "
            f"   WHERE np.notebook_id IN ({ids_literal})'"
            f") "
            f"WHERE length(word) > 2 "
            f"ORDER BY ndoc DESC, nentry DESC "
            f"LIMIT $1",
            max_clusters * 5,  # fetch more to account for stop word filtering
        )

    # Get accessible table IDs
    tbl_ids = await pool.fetch(
        "SELECT t.id FROM tables t "
        "WHERE t.workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = $1) "
        "   OR (t.workspace_id IS NULL AND t.created_by = $1)",
        user_id,
    )
    tbl_id_list = [str(r["id"]) for r in tbl_ids]

    table_terms: list = []
    if tbl_id_list:
        ids_literal = ",".join(f"'{uid}'" for uid in tbl_id_list)
        table_terms = await pool.fetch(
            f"SELECT word, ndoc, nentry "
            f"FROM ts_stat("
            f"  'SELECT to_tsvector(''english'', tr.data::text) "
            f"   FROM table_rows tr "
            f"   WHERE tr.table_id IN ({ids_literal})'"
            f") "
            f"WHERE length(word) > 2 "
            f"ORDER BY ndoc DESC, nentry DESC "
            f"LIMIT $1",
            max_clusters * 5,
        )

    # Merge term counts, filtering out stop stems
    term_counts: dict[str, dict] = {}
    for row in page_terms:
        w = row["word"]
        if w in _STOP_STEMS:
            continue
        term_counts[w] = {
            "notebook_pages": row["ndoc"],
            "table_rows": 0,
            "total": row["ndoc"],
        }
    for row in table_terms:
        w = row["word"]
        if w in _STOP_STEMS:
            continue
        if w in term_counts:
            term_counts[w]["table_rows"] = row["ndoc"]
            term_counts[w]["total"] += row["ndoc"]
        else:
            term_counts[w] = {
                "notebook_pages": 0,
                "table_rows": row["ndoc"],
                "total": row["ndoc"],
            }

    # Sort by total and take top N
    top_terms = sorted(term_counts.items(), key=lambda x: x[1]["total"], reverse=True)[
        :max_clusters
    ]

    if not top_terms:
        result = {"clusters": []}
        _density_cache[cache_key] = (now, result)
        return result

    # Batch enrichment: get sample titles + timestamps for ALL terms in one query
    # Uses LATERAL join to get top 3 matching pages per term
    words = [w for w, _ in top_terms]
    enrichment: dict[str, list[dict]] = {w: [] for w in words}

    if nb_id_list:
        rows = await pool.fetch(
            "SELECT term.word, np.name, np.created_at, np.updated_at "
            "FROM unnest($1::text[]) AS term(word) "
            "CROSS JOIN LATERAL ("
            "  SELECT np.name, np.created_at, np.updated_at "
            "  FROM notebook_pages np "
            "  WHERE np.notebook_id = ANY($2::uuid[]) "
            "    AND to_tsvector('english', np.content_markdown) @@ plainto_tsquery('english', term.word) "
            "  ORDER BY np.updated_at DESC "
            "  LIMIT 3"
            ") np",
            words, nb_id_list,
        )
        for r in rows:
            enrichment[r["word"]].append(r)

    # Map stems back to surface forms by finding the most common original word
    # that reduces to each stem
    surface_forms: dict[str, str] = {}
    if nb_id_list:
        # For each stem, find the most frequent original word in page content
        surface_rows = await pool.fetch(
            "SELECT stem.word AS stem, token, COUNT(*) AS freq "
            "FROM unnest($1::text[]) AS stem(word) "
            "CROSS JOIN LATERAL ("
            "  SELECT DISTINCT ON (token) token "
            "  FROM ("
            "    SELECT ts_lexize('english_stem', token)::text[] AS lexemes, token "
            "    FROM ("
            "      SELECT alias AS token "
            "      FROM ts_debug('english', ("
            "        SELECT string_agg(np.content_markdown, ' ') "
            "        FROM notebook_pages np "
            "        WHERE np.notebook_id = ANY($2::uuid[])"
            "      ))"
            "      WHERE alias IS NOT NULL"
            "    ) raw "
            "    WHERE ts_lexize('english_stem', token) IS NOT NULL"
            "  ) lexed "
            "  WHERE lexemes[1] = stem.word "
            "  LIMIT 10"
            ") surface "
            "GROUP BY stem.word, token "
            "ORDER BY stem.word, freq DESC",
            words, nb_id_list,
        )
        for r in surface_rows:
            stem = r["stem"]
            if stem not in surface_forms:
                surface_forms[stem] = r["token"]

    # Build clusters
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

        # Use surface form if available, otherwise capitalize the stem
        label = surface_forms.get(word, word)

        clusters.append({
            "label": label,
            "count": counts["total"],
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
    """2D UMAP projection of embeddings for the space explorer."""
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

    # Run UMAP projection
    try:
        from umap import UMAP

        embeddings_matrix = np.stack([item["embedding"] for item in all_items])
        n_neighbors = min(15, len(all_items) - 1)
        if n_neighbors < 2:
            # Not enough points for UMAP, just spread randomly
            coords = np.random.uniform(-1, 1, (len(all_items), 2))
        else:
            reducer = UMAP(n_components=2, n_neighbors=n_neighbors, min_dist=0.1, random_state=42)
            coords = reducer.fit_transform(embeddings_matrix)
            # Normalize to [-1, 1]
            for dim in range(2):
                mn, mx = coords[:, dim].min(), coords[:, dim].max()
                rng = mx - mn if mx != mn else 1.0
                coords[:, dim] = 2.0 * (coords[:, dim] - mn) / rng - 1.0
    except ImportError:
        logger.warning("umap-learn not installed, using PCA fallback")
        # PCA fallback: center, compute top 2 eigenvectors
        embeddings_matrix = np.stack([item["embedding"] for item in all_items])
        mean = embeddings_matrix.mean(axis=0)
        centered = embeddings_matrix - mean
        if centered.shape[0] > 1:
            cov = np.cov(centered.T)
            eigenvalues, eigenvectors = np.linalg.eigh(cov)
            top2 = eigenvectors[:, -2:]
            coords = centered @ top2
            for dim in range(2):
                mn, mx = coords[:, dim].min(), coords[:, dim].max()
                rng = mx - mn if mx != mn else 1.0
                coords[:, dim] = 2.0 * (coords[:, dim] - mn) / rng - 1.0
        else:
            coords = np.zeros((len(all_items), 2))

    # Build points
    points = []
    for i, item in enumerate(all_items):
        points.append({
            "id": item["id"],
            "x": round(float(coords[i, 0]), 4),
            "y": round(float(coords[i, 1]), 4),
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
