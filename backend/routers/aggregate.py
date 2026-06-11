"""Aggregate router: cross-workspace indexes for the authenticated user."""

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
    """Every page across every workspace the user is a member of."""
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
    """Session events across all accessible workspaces, with filters."""
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
    """Recently-viewed objects across all workspaces, most recent first.

    Includes objects in workspaces the user isn't a member of (shared items),
    which the Shared-with-me Recent strip resolves against the share list.
    """
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT object_id, kind, workspace_id FROM user_recents "
        "WHERE user_id = $1 ORDER BY viewed_at DESC LIMIT 30",
        current_user["id"],
    )
    return [
        {
            "object_id": r["object_id"],
            "kind": r["kind"],
            "workspace_id": r["workspace_id"],
        }
        for r in rows
    ]


@router.get("/activity")
async def list_activity(
    limit: int = Query(50, ge=1, le=200),
    before: datetime | None = Query(None),
    workspace_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Recent product activity across accessible workspaces, cursor-paginated by ts."""
    pool = get_pool()
    events = await pool.fetch(
        """
        WITH member_workspaces AS (
          SELECT w.id, w.name
          FROM workspaces w
          JOIN workspace_members wm ON wm.workspace_id = w.id
          WHERE wm.user_id = $1
          AND ($3::uuid IS NULL OR w.id = $3)
        ),
        -- Member workspaces plus any workspace that has shared content with the
        -- user. Page/file rows still pass readable_content_condition, so a share
        -- only surfaces the specific shared rows — never the whole workspace.
        accessible_workspaces AS (
          SELECT w.id, w.name
          FROM workspaces w
          WHERE w.id IN """
        + permission_service.accessible_workspace_ids_sql(1)
        + """
          AND ($3::uuid IS NULL OR w.id = $3)
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
                 aw.id AS workspace_id,
                 aw.name AS workspace_name
          FROM history_events he
          JOIN member_workspaces aw ON aw.id = he.workspace_id
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
                 aw.id AS workspace_id,
                 aw.name AS workspace_name
          FROM pages p
          JOIN accessible_workspaces aw ON aw.id = p.workspace_id
          WHERE COALESCE(p.metadata->>'shared_in_cartridge_id', '') = ''
            AND p.deleted_at IS NULL
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
                 aw.id AS workspace_id,
                 aw.name AS workspace_name
          FROM files f
          JOIN accessible_workspaces aw ON aw.id = f.workspace_id
          WHERE f.deleted_at IS NULL
            AND """
        + permission_service.readable_content_condition("file", "f", 1)
        + """
        )
        UNION ALL
        (
          SELECT 'member.joined' AS kind,
                 wm.joined_at AS ts,
                 wm.user_id AS actor_id,
                 wm.user_id::text AS target_id,
                 '' AS target_label,
                 aw.id AS workspace_id,
                 aw.name AS workspace_name
          FROM workspace_members wm
          JOIN member_workspaces aw ON aw.id = wm.workspace_id
        )
        ) ev
        WHERE ($4::timestamptz IS NULL OR ev.ts < $4)
        ORDER BY ts DESC LIMIT $2
        """,
        current_user["id"],
        limit + 1,
        workspace_id,
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
                "workspace_id": r["workspace_id"],
                "workspace_name": r["workspace_name"],
            }
            for r in events
        ],
        "has_more": has_more,
    }


@router.get("/tables")
async def list_all_tables(current_user: dict = Depends(get_current_user)):
    """All tables from workspaces + personal."""
    tables = await table_service.list_all_user_tables(current_user["id"])
    return {"tables": tables}


@router.get("/overview")
async def overview_counts(current_user: dict = Depends(get_current_user)):
    """Page / file / session counts for the 'Your brain' vitals, spanning the
    user's own content plus everything shared with them."""
    return await analytics_service.get_overview_counts(current_user["id"])


async def _verify_workspace_access(workspace_id: UUID, user_id: UUID) -> None:
    """Raise 403 if the user isn't a member of the workspace."""
    from fastapi import HTTPException

    from ..services import permission_service

    role = await permission_service.get_workspace_role(workspace_id, user_id)
    if role is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")


async def _verify_scope(
    workspace_id: UUID | None,
    cartridge_id: UUID | None,
    user_id: UUID,
) -> None:
    """workspace_id and cartridge_id are mutually exclusive. Verify access to whichever was passed."""
    from fastapi import HTTPException

    from ..services import cartridge_service

    if workspace_id is not None and cartridge_id is not None:
        raise HTTPException(
            status_code=400, detail="workspace_id and cartridge_id are mutually exclusive"
        )
    if workspace_id is not None:
        await _verify_workspace_access(workspace_id, user_id)
        return
    if cartridge_id is not None:
        if not await cartridge_service.user_can_read(cartridge_id, user_id):
            raise HTTPException(status_code=403, detail="Cannot read this Stash")


@router.get("/activity-timeline")
async def activity_timeline(
    days: int = Query(30, ge=1, le=365),
    bucket: str = Query("day"),
    workspace_id: UUID | None = Query(None),
    cartridge_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Human + coding-agent session commits bucketed by time for the dashboard timeline."""
    await _verify_scope(workspace_id, cartridge_id, current_user["id"])
    return await analytics_service.get_activity_timeline(
        current_user["id"],
        days=days,
        bucket=bucket,
        workspace_id=workspace_id,
        cartridge_id=cartridge_id,
    )


@router.get("/knowledge-density")
async def knowledge_density(
    max_clusters: int = Query(20, ge=1, le=50),
    workspace_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Topic clusters for the knowledge density heatmap."""
    if workspace_id is not None:
        await _verify_workspace_access(workspace_id, current_user["id"])
    return await analytics_service.get_knowledge_density(
        current_user["id"],
        max_clusters=max_clusters,
        workspace_id=workspace_id,
    )


@router.get("/embedding-projection")
async def embedding_projection(
    max_points: int = Query(500, ge=1, le=2000),
    source: str | None = Query(None),
    workspace_id: UUID | None = Query(None),
    cartridge_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """2D UMAP projection of embeddings for the space explorer."""
    await _verify_scope(workspace_id, cartridge_id, current_user["id"])
    return await analytics_service.get_embedding_projection(
        current_user["id"],
        max_points=max_points,
        source=source,
        workspace_id=workspace_id,
        cartridge_id=cartridge_id,
    )
