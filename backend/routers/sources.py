"""Connected-source registry endpoints.

A source is added per workspace but USER-SCOPED — it belongs to the member who
connects it (`owner_user_id = current_user`) and only they can list, read, or
remove it. The agent reaches a source's indexed content through the source tools;
these endpoints just manage the registry. Indexing (sync tasks) is wired per
source type in later phases.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..celery_app import celery
from ..integrations import storage as integration_storage
from ..integrations.registry import get_provider
from ..services import permission_service, source_service

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/sources", tags=["sources"])


async def _require_member(workspace_id: UUID, user_id: UUID) -> None:
    if await permission_service.get_workspace_role(workspace_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")


class AddSourceRequest(BaseModel):
    source_type: str
    # Optional for Slack/Granola — their workspace id + name are resolved from
    # the connected token (the user can't easily supply them).
    external_ref: str | None = None
    display_name: str | None = None


async def _resolve_slack_source(user_id) -> tuple[str, str]:
    """Slack source external_ref = team id, display_name = team name, both from
    the connected user token."""
    token = await integration_storage.get_valid_token(user_id, "slack")
    info = await get_provider("slack").team_info(token)
    return info["team_id"], info["team_name"]


async def _resolve_granola_source(user_id) -> tuple[str, str]:
    """Granola source external_ref = workspace id, from the connected token."""
    token = await integration_storage.get_valid_token(user_id, "granola")
    info = await get_provider("granola").account_info(token)
    return info["workspace_id"], info["workspace_name"]


@router.get("")
async def list_sources(workspace_id: UUID, current_user: dict = Depends(get_current_user)):
    """Sources this user can see here: native files + sessions, plus their own
    connected sources."""
    await _require_member(workspace_id, current_user["id"])
    return {"sources": await source_service.list_sources(workspace_id, current_user["id"])}


@router.post("")
async def add_source(
    workspace_id: UUID,
    body: AddSourceRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_member(workspace_id, current_user["id"])
    if body.source_type not in source_service.SOURCE_CAPABILITY:
        raise HTTPException(status_code=400, detail=f"unknown source type: {body.source_type}")

    external_ref = body.external_ref
    display_name = body.display_name
    if body.source_type == "slack" and not external_ref:
        external_ref, resolved_name = await _resolve_slack_source(current_user["id"])
        display_name = display_name or resolved_name
    elif body.source_type == "granola" and not external_ref:
        external_ref, resolved_name = await _resolve_granola_source(current_user["id"])
        display_name = display_name or resolved_name

    if not external_ref:
        raise HTTPException(status_code=400, detail="external_ref is required")
    return await source_service.create_source(
        workspace_id=workspace_id,
        owner_user_id=current_user["id"],
        source_type=body.source_type,
        external_ref=external_ref,
        display_name=display_name or external_ref,
    )


@router.post("/{source_id}/sync")
async def sync_source_now(
    workspace_id: UUID,
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Trigger an immediate re-index of an owned source."""
    await _require_member(workspace_id, current_user["id"])
    if await source_service.get_owned_source(source_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Source not found")
    result = celery.send_task(
        "backend.tasks.sources.sync_source",
        kwargs={"source_id": str(source_id)},
    )
    return {"task_id": result.id}


@router.delete("/{source_id}")
async def remove_source(
    workspace_id: UUID,
    source_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _require_member(workspace_id, current_user["id"])
    deleted = await source_service.delete_source(source_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"deleted": True, "source_id": str(source_id)}
