"""Aggregate router: cross-scope indexes for the authenticated user."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
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
    """Every page across every scope the user is a member of."""
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

    Includes objects in scopes the user isn't a member of (shared items),
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


@router.get("/activity")
async def list_activity(
    limit: int = Query(50, ge=1, le=200),
    before: datetime | None = Query(None),
    owner_user_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Recent product activity across accessible scopes, cursor-paginated by ts."""
    pool = get_pool()
    events = await pool.fetch(
        """
        WITH member_scopes AS (
          SELECT u.id, u.name
          FROM users u
          WHERE u.id = $1
          AND ($3::uuid IS NULL OR u.id = $3)
        ),
        -- The user's own scope plus any scope that has shared content with the
        -- user. Page/file rows still pass readable_content_condition, so a share
        -- only surfaces the specific shared rows — never the whole scope.
        accessible_scopes AS (
          SELECT u.id, u.name
          FROM users u
          WHERE u.id IN """
        + permission_service.accessible_scope_ids_sql(1)
        + """
          AND ($3::uuid IS NULL OR u.id = $3)
        )
        SELECT * FROM (
        (
          SELECT 'session.uploaded' AS kind,
                 MAX(he.created_at) AS ts,
                 (
                   ARRAY_AGG(he.created_by ORDER BY he.created_at DESC)
                   FILTER (WHERE he.created_by IS NOT NULL)
                 )[1] AS actor_id,
                 he.session_id AS target_id,
                 (
                   ARRAY_AGG(he.agent_name ORDER BY he.created_at DESC)
                   FILTER (WHERE he.agent_name IS NOT NULL)
                 )[1] || ': ' || he.session_id AS target_label,
                 aw.id AS owner_user_id,
                 aw.name AS owner_name
          FROM history_events he
          JOIN member_scopes aw ON aw.id = he.owner_user_id
          WHERE he.session_id IS NOT NULL
            AND """
        + memory_service.readable_session_event_condition("he", 1)
        + """
          GROUP BY aw.id, aw.name, he.session_id
        )
        UNION ALL
        (
          SELECT 'page.updated' AS kind,
                 p.updated_at AS ts,
                 COALESCE(p.updated_by, p.created_by) AS actor_id,
                 p.id::text AS target_id,
                 p.name AS target_label,
                 aw.id AS owner_user_id,
                 aw.name AS owner_name
          FROM pages p
          JOIN accessible_scopes aw ON aw.id = p.owner_user_id
          WHERE p.deleted_at IS NULL
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
                 aw.id AS owner_user_id,
                 aw.name AS owner_name
          FROM files f
          JOIN accessible_scopes aw ON aw.id = f.owner_user_id
          WHERE f.deleted_at IS NULL
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
        owner_user_id,
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


@router.get("/overview")
async def overview_counts(current_user: dict = Depends(get_current_user)):
    """Page / file / session counts for the 'Your brain' vitals, spanning the
    user's own content plus everything shared with them."""
    return await analytics_service.get_overview_counts(current_user["id"])


async def _verify_scope_access(owner_user_id: UUID, user_id: UUID) -> None:
    """Raise 403 if the user isn't a member of the scope."""
    from fastapi import HTTPException

    from ..services import user_scope_service

    if not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not a member of this scope")


@router.get("/activity-timeline")
async def activity_timeline(
    days: int = Query(30, ge=1, le=365),
    bucket: str = Query("day"),
    owner_user_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Human + coding-agent session commits bucketed by time for the dashboard timeline."""
    if owner_user_id is not None:
        await _verify_scope_access(owner_user_id, current_user["id"])
    return await analytics_service.get_activity_timeline(
        current_user["id"],
        days=days,
        bucket=bucket,
        owner_user_id=owner_user_id,
    )


@router.get("/knowledge-density")
async def knowledge_density(
    max_clusters: int = Query(20, ge=1, le=50),
    owner_user_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Topic clusters for the knowledge density heatmap."""
    if owner_user_id is not None:
        await _verify_scope_access(owner_user_id, current_user["id"])
    return await analytics_service.get_knowledge_density(
        current_user["id"],
        max_clusters=max_clusters,
        owner_user_id=owner_user_id,
    )


@router.get("/embedding-projection")
async def embedding_projection(
    max_points: int = Query(500, ge=1, le=2000),
    source: str | None = Query(None),
    owner_user_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """2D UMAP projection of embeddings for the space explorer."""
    if owner_user_id is not None:
        await _verify_scope_access(owner_user_id, current_user["id"])
    return await analytics_service.get_embedding_projection(
        current_user["id"],
        max_points=max_points,
        source=source,
        owner_user_id=owner_user_id,
    )
