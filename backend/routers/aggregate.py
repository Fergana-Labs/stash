"""Aggregate router: cross-scope indexes for the authenticated user."""

from datetime import datetime
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user, get_scope
from ..database import get_pool
from ..models import UserPageEntry, UserPageListResponse
from ..services import (
    analytics_service,
    files_tree_service,
    memory_service,
    session_title_service,
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


@router.get("/recent-activity")
async def list_recent_activity(
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    scope_user_id: UUID = Depends(get_scope),
):
    """The active scope's latest agent sessions and newly-created Skills."""
    pool = get_pool()
    sessions = [
        dict(row)
        for row in await pool.fetch(
            """
        WITH recent_sessions AS (
          SELECT session_id, last_event_at, created_by
          FROM sessions
          WHERE owner_user_id = $1 AND deleted_at IS NULL
          ORDER BY last_event_at DESC
          LIMIT $2
        )
        SELECT s.session_id, s.last_event_at, author.display_name AS author_name,
               COUNT(he.id)::int AS event_count,
               (ARRAY_AGG(NULLIF(he.metadata->>'model', '') ORDER BY he.created_at DESC)
                FILTER (WHERE NULLIF(he.metadata->>'model', '') IS NOT NULL))[1] AS model,
               (ARRAY_AGG(LEFT(he.content, 240) ORDER BY
                 CASE WHEN he.event_type IN ('user_message','user_prompt','prompt','message','user')
                      THEN 0 ELSE 1 END, he.created_at, he.id)
                FILTER (WHERE NULLIF(BTRIM(he.content), '') IS NOT NULL))[1] AS title_source
        FROM recent_sessions s
        JOIN history_events he ON he.owner_user_id = $1 AND he.session_id = s.session_id
        JOIN users author ON author.id = s.created_by
        GROUP BY s.session_id, s.last_event_at, author.display_name
        ORDER BY s.last_event_at DESC
        """,
            scope_user_id,
            limit,
        )
    ]
    titles = await session_title_service.titles_for_sessions(scope_user_id, sessions)
    skills = await pool.fetch(
        "SELECT id, name, skill_created_at FROM folders "
        "WHERE owner_user_id = $1 AND is_skill ORDER BY skill_created_at DESC LIMIT $2",
        scope_user_id,
        limit,
    )
    events = [
        {
            "kind": "session",
            "ts": row["last_event_at"],
            "title": titles[row["session_id"]],
            "subtitle": (
                f"{row['author_name']}'s {row['model']}"
                if row["model"]
                else f"{row['author_name']} · model unavailable"
            ),
            "href": f"/sessions/{quote(row['session_id'], safe='')}",
        }
        for row in sessions
    ] + [
        {
            "kind": "skill.created",
            "ts": row["skill_created_at"],
            "title": row["name"],
            "subtitle": "New Skill",
            "href": f"/skills/folder/{row['id']}",
        }
        for row in skills
    ]
    events.sort(key=lambda event: event["ts"], reverse=True)
    return {"events": events[:limit]}


@router.get("/tables")
async def list_all_tables(current_user: dict = Depends(get_current_user)):
    """All tables from shared scopes + personal."""
    tables = await table_service.list_all_user_tables(current_user["id"])
    return {"tables": tables}


@router.get("/vitals")
async def overview_counts(current_user: dict = Depends(get_current_user)):
    """Page / file / session counts for the 'Your brain' vitals, spanning the
    user's own content plus everything shared with them. Distinct from the scope
    `/overview` payload in user_knowledge (same prefix — the paths must not
    collide, or whichever registers first shadows the other)."""
    return await analytics_service.get_overview_counts(current_user["id"])


async def _verify_scope_access(owner_user_id: UUID, user_id: UUID) -> None:
    """Raise 403 if the user doesn't own the scope."""
    from fastapi import HTTPException

    from ..services import user_scope_service

    if not await user_scope_service.is_owner(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not the owner of this scope")


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
    """3D UMAP projection of embeddings for the space explorer."""
    if owner_user_id is not None:
        await _verify_scope_access(owner_user_id, current_user["id"])
    return await analytics_service.get_embedding_projection(
        current_user["id"],
        max_points=max_points,
        source=source,
        owner_user_id=owner_user_id,
    )
