"""Aggregate router: cross-scope indexes for the authenticated user."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user, get_scope
from ..database import get_pool
from ..models import UserPageEntry, UserPageListResponse
from ..services import (
    analytics_service,
    files_tree_service,
    memory_service,
    permission_service,
    table_service,
)

router = APIRouter(prefix="/api/v1/me", tags=["aggregate"])


@router.get("/pages", response_model=UserPageListResponse)
async def list_all_pages(current_user: dict = Depends(get_current_user)):
    """Every page across every scope the user can access."""
    rows = await files_tree_service.list_user_pages(current_user["id"])
    return UserPageListResponse(pages=[UserPageEntry(**r) for r in rows])


@router.get("/session-events")
async def list_all_session_events(
    agent_name: str | None = Query(None),
    event_type: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(get_current_user),
):
    """Session events across all accessible scopes, with filters."""
    events, has_more = await memory_service.query_all_user_events(
        current_user["id"],
        agent_name=agent_name,
        event_type=event_type,
        after=after,
        before=before,
        limit=limit,
        order=order,
    )
    return {"events": events, "has_more": has_more}


@router.get("/recents")
async def list_my_recents(current_user: dict = Depends(get_current_user)):
    """Recently-viewed objects across all scopes, most recent first.

    Includes objects in other users' scopes (shared items),
    which the Shared-with-me Recent strip resolves against the share list.
    """
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT object_id, kind, owner_user_id FROM user_recents "
        "WHERE user_id = $1 ORDER BY viewed_at DESC LIMIT 30",
        current_user["id"],
    )
    return [
        {
            "object_id": r["object_id"],
            "kind": r["kind"],
            "owner_user_id": r["owner_user_id"],
        }
        for r in rows
    ]


@router.get("/file-activity")
async def list_file_activity(
    limit: int = Query(50, ge=1, le=200),
    before: datetime | None = Query(None),
    current_user: dict = Depends(get_current_user),
    scope: UUID = Depends(get_scope),
):
    """New and edited files and pages across accessible scopes, cursor-paginated
    by ts. Memory subtrees are excluded: curation output is the curator log's
    story, not file activity. Every scope's Memory is excluded, not just the
    caller's — a workspace scope's nightly curation churn would otherwise flood
    the feed of every member who can read it."""
    pool = get_pool()
    events = await pool.fetch(
        """
        WITH RECURSIVE accessible_scopes AS (
          -- The user's own scope plus any scope that has shared content with
          -- the user. Page/file rows still pass readable_content_condition, so
          -- a share only surfaces the specific shared rows — never the whole
          -- scope.
          SELECT u.id, u.name
          FROM users u
          WHERE u.id IN """
        + permission_service.accessible_scope_ids_sql(1)
        + """
          AND ($3::uuid IS NULL OR u.id = $3)
        ),
        memory_folders AS (
          SELECT mf.id FROM folders mf
          JOIN accessible_scopes aw ON aw.id = mf.owner_user_id
          WHERE mf.is_memory
          UNION
          SELECT mf.id FROM folders mf
          JOIN memory_folders m ON m.id = mf.parent_folder_id
        )
        SELECT * FROM (
        (
          SELECT 'page.updated' AS kind,
                 p.updated_at AS ts,
                 COALESCE(p.updated_by, p.created_by) AS actor_id,
                 p.id::text AS target_id,
                 p.name AS target_label,
                 p.last_edit_agent_name AS agent_name,
                 aw.id AS owner_user_id,
                 aw.name AS owner_name
          FROM pages p
          JOIN accessible_scopes aw ON aw.id = p.owner_user_id
          WHERE p.deleted_at IS NULL
            AND NOT EXISTS (SELECT 1 FROM memory_folders m WHERE m.id = p.folder_id)
            AND """
        + permission_service.readable_content_condition("page", "p", 1)
        + """
        )
        UNION ALL
        (
          SELECT 'file.uploaded' AS kind,
                 f.created_at AS ts,
                 f.uploaded_by AS actor_id,
                 f.id::text AS target_id,
                 f.name AS target_label,
                 NULL::text AS agent_name,
                 aw.id AS owner_user_id,
                 aw.name AS owner_name
          FROM files f
          JOIN accessible_scopes aw ON aw.id = f.owner_user_id
          WHERE f.deleted_at IS NULL
            AND NOT EXISTS (SELECT 1 FROM memory_folders m WHERE m.id = f.folder_id)
            AND """
        + permission_service.readable_content_condition("file", "f", 1)
        + """
        )
        ) ev
        WHERE ($4::timestamptz IS NULL OR ev.ts < $4)
        ORDER BY ts DESC LIMIT $2
        """,
        current_user["id"],
        limit + 1,
        scope,
        before,
    )
    has_more = len(events) > limit
    if has_more:
        events = events[:limit]
    user_ids = list({r["actor_id"] for r in events if r["actor_id"]})
    users = {}
    if user_ids:
        rows = await pool.fetch(
            "SELECT id, name, display_name FROM users WHERE id = ANY($1::uuid[])",
            user_ids,
        )
        users = {r["id"]: {"name": r["name"], "display_name": r["display_name"]} for r in rows}

    return {
        "events": [
            {
                "kind": r["kind"],
                "ts": r["ts"],
                "actor": users[r["actor_id"]],
                "target_id": r["target_id"],
                "target_label": r["target_label"],
                "agent_name": r["agent_name"],
                "owner_user_id": r["owner_user_id"],
                "owner_name": r["owner_name"],
            }
            for r in events
        ],
        "has_more": has_more,
    }


@router.get("/tables")
async def list_all_tables(current_user: dict = Depends(get_current_user)):
    """All tables from shared scopes + personal."""
    tables = await table_service.list_all_user_tables(current_user["id"])
    return {"tables": tables}


@router.get("/vitals")
async def overview_counts(scope: UUID = Depends(get_scope)):
    """Page / file / session counts for the 'Your brain' vitals — the active
    scope only, so a stash's home page never counts another stash's content.
    Distinct from the scope `/overview` payload in user_knowledge (same prefix
    — the paths must not collide, or whichever registers first shadows the
    other)."""
    return await analytics_service.get_overview_counts(scope)


@router.get("/activity-timeline")
async def activity_timeline(
    days: int = Query(30, ge=1, le=365),
    bucket: str = Query("day"),
    current_user: dict = Depends(get_current_user),
    scope: UUID = Depends(get_scope),
):
    """Human + coding-agent session commits bucketed by time for the dashboard timeline."""
    return await analytics_service.get_activity_timeline(
        current_user["id"],
        days=days,
        bucket=bucket,
        owner_user_id=scope,
    )


@router.get("/knowledge-density")
async def knowledge_density(
    max_clusters: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    scope: UUID = Depends(get_scope),
):
    """Topic clusters for the knowledge density heatmap."""
    return await analytics_service.get_knowledge_density(
        current_user["id"],
        max_clusters=max_clusters,
        owner_user_id=scope,
    )


@router.get("/embedding-projection")
async def embedding_projection(
    max_points: int = Query(500, ge=1, le=2000),
    source: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    scope: UUID = Depends(get_scope),
):
    """3D UMAP projection of embeddings for the space explorer."""
    return await analytics_service.get_embedding_projection(
        current_user["id"],
        max_points=max_points,
        source=source,
        owner_user_id=scope,
    )
