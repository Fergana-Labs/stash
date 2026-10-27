"""Indexed candidate retrieval over the same publication boundary as VFS reads.

Only title/body are searchable: shared metadata is not approved for publication.
Results are candidates, not evidence that the requested fact exists or is absent.
"""

from uuid import UUID

from ..database import get_pool
from . import security_audit_service, shared_wiki_privacy

# Keep in sync with migration 0256. Metadata must never enter this vector.
BODY_TEXT = (
    "CASE WHEN content_type = 'html' "
    "THEN regexp_replace(COALESCE(content_html, ''), '<[^>]+>', ' ', 'g') "
    "ELSE COALESCE(content_markdown, '') END"
)
SEARCH_VECTOR = (
    "setweight(to_tsvector('english', COALESCE(name, '')), 'A') || "
    f"setweight(to_tsvector('english', {BODY_TEXT}), 'B')"
)


async def search(
    workspace_id: str, external_id: str | None, query: str, scope: str, limit: int, owner_id: UUID
) -> dict:
    async with get_pool().acquire() as conn:
        # Permission/approval predicates are applied BEFORE ranking and LIMIT.
        # Do not use generic owner search: a workspace owner owns every customer's wiki.
        rows = await conn.fetch(
            "WITH RECURSIVE shared_tree AS ("
            "SELECT f.id,w.scope_user_id AS owner FROM workspaces w JOIN folders f "
            "ON f.id=w.external_wiki_folder_id AND f.owner_user_id=w.scope_user_id "
            "WHERE w.id=$1 UNION SELECT f.id,t.owner FROM folders f JOIN shared_tree t "
            "ON f.parent_folder_id=t.id WHERE f.owner_user_id=t.owner), "
            "private_tree AS ("
            "SELECT f.id,w.scope_user_id AS owner FROM workspaces w JOIN end_users e "
            "ON e.workspace_id=w.id JOIN folders f ON f.id=e.wiki_folder_id "
            "AND f.owner_user_id=w.scope_user_id WHERE w.id=$1 AND e.external_id=$2 "
            "UNION SELECT f.id,t.owner FROM folders f JOIN private_tree t "
            "ON f.parent_folder_id=t.id WHERE f.owner_user_id=t.owner), "
            "query AS (SELECT plainto_tsquery('english',$3) AS q), "
            "eligible AS (SELECT p.*,CASE WHEN priv.id IS NOT NULL THEN 'private' "
            "ELSE 'shared' END AS scope FROM pages p "
            "LEFT JOIN private_tree priv ON p.folder_id=priv.id AND p.owner_user_id=priv.owner "
            "LEFT JOIN shared_tree shared ON p.folder_id=shared.id AND p.owner_user_id=shared.owner "
            "LEFT JOIN shared_wiki_reviews r ON r.page_id=p.id AND r.workspace_id=$4 "
            "AND r.folder_id=p.folder_id AND r.policy_version=$5 "
            "AND r.name=p.name AND r.content_markdown=p.content_markdown "
            "WHERE p.deleted_at IS NULL AND ("
            "(priv.id IS NOT NULL AND $6 IN ('wiki','private')) OR "
            "(shared.id IS NOT NULL AND $6 IN ('wiki','shared') AND r.page_id IS NOT NULL "
            "AND p.content_type='markdown' AND p.end_user_id IS NULL))) "
            "SELECT id,name,scope,owner_user_id,"
            f"ts_rank(({SEARCH_VECTOR}),q) AS rank, "
            f"strpos(lower(COALESCE(name,'') || E'\\n' || ({BODY_TEXT})),lower($3))>0 AS exact, "
            f"left(ts_headline('english',({BODY_TEXT}),q,"
            "'MaxWords=45,MinWords=15,StartSel=<<,StopSel=>>'),2000) AS excerpt "
            f"FROM eligible CROSS JOIN query WHERE ({SEARCH_VECTOR}) @@ q "
            "ORDER BY exact DESC,(scope='private') DESC,rank DESC,id LIMIT $7",
            UUID(workspace_id),
            external_id,
            query,
            UUID(workspace_id),
            shared_wiki_privacy.POLICY_VERSION,
            scope,
            limit + 1,
        )
    await security_audit_service.record_event(
        action="source.searched",
        actor_user_id=owner_id,
        owner_user_id=owner_id,
        target_type="vfs",
        target_id="wiki-index",
        metadata={
            "query_hash": security_audit_service.hash_value(query),
            "retrieval": "indexed_wiki",
            "scope": scope,
            "returned": min(len(rows), limit),
            "has_more": len(rows) > limit,
        },
    )
    return {
        "query": query,
        "scope": scope,
        "has_more": len(rows) > limit,
        "results": [
            {"id": str(r["id"]), "name": r["name"], "scope": r["scope"], "excerpt": r["excerpt"]}
            for r in rows[:limit]
        ],
        "coverage": "Ranked wiki candidates only; files, transcripts and connected sources are not searched.",
        "guidance": "Read the strongest candidates before answering. If inconclusive, narrow the query or search files/transcripts. An empty candidate list does not prove absence of the information.",
    }
