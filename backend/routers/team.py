"""Team endpoints: the member-facing view of a workspace.

`/me/team` resolves "my team" from workspace membership. A caller in exactly
one workspace never passes an id; a caller in several must say which — no
guessing, no first-match fallback.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..services import team_service, workspace_service

router = APIRouter(prefix="/api/v1/me/team", tags=["team"])


async def _resolve_workspace(current_user: dict, workspace_id: UUID | None) -> dict:
    workspaces = await workspace_service.list_for_user(current_user["id"])
    if not workspaces:
        raise HTTPException(status_code=404, detail="You are not in a workspace")
    if workspace_id is None:
        if len(workspaces) > 1:
            raise HTTPException(
                status_code=400,
                detail="You are in several workspaces; pass workspace_id",
            )
        return workspaces[0]
    for workspace in workspaces:
        if workspace["id"] == workspace_id:
            return workspace
    raise HTTPException(status_code=404, detail="You are not in that workspace")


@router.get("")
async def get_my_team(
    workspace_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    workspace = await _resolve_workspace(current_user, workspace_id)
    members = await team_service.list_members(workspace["id"])
    return {
        "id": str(workspace["id"]),
        "name": workspace["name"],
        "domain": workspace["domain"],
        "scope_user_id": str(workspace["scope_user_id"]),
        "members": [
            {
                "id": str(member["id"]),
                "name": member["name"],
                "display_name": member["display_name"],
                "email": member["email"],
            }
            for member in members
        ],
    }


@router.get("/skills")
async def list_team_skills(
    workspace_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """The team's skill library — a store of its own, separate from the wiki
    (procedural how-tos every agent should carry, vs. facts to look up)."""
    workspace = await _resolve_workspace(current_user, workspace_id)
    data = await team_service.list_team_skills(workspace["scope_user_id"])
    return {
        "folder_id": str(data["folder"]["id"]),
        "skills": [
            {
                "id": str(page["id"]),
                "name": page["name"],
                "updated_at": page["updated_at"],
            }
            for page in data["skills"]
        ],
    }


@router.get("/analytics")
async def team_analytics(
    workspace_id: UUID | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Per-member session counts and estimated token volume. Deliberately
    metadata-only: totals and timestamps, never titles or content — the audit
    surface must not leak what the privacy default protects."""
    workspace = await _resolve_workspace(current_user, workspace_id)
    stats = await team_service.member_session_stats(workspace["id"])
    return {
        "members": [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "display_name": row["display_name"],
                "sessions_total": row["sessions_total"],
                "sessions_7d": row["sessions_7d"],
                "sessions_30d": row["sessions_30d"],
                "est_tokens_30d": row["est_tokens_30d"],
                "last_session_at": row["last_session_at"],
            }
            for row in stats
        ]
    }
