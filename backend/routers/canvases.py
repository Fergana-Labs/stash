"""Canvas router: agent-generated generative-UI artifacts.

Canvases are normally created/updated by the agent (via its canvas tools), so
these endpoints are read-leaning: the frontend opens a canvas by id and lists a
chat's canvases. Write endpoints exist for completeness and direct editing.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..models import (
    CanvasCreateRequest,
    CanvasListResponse,
    CanvasResponse,
    CanvasUpdateRequest,
)
from ..services import canvas_service, workspace_service

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/canvases", tags=["canvases"])
router = APIRouter(prefix="/api/v1/canvases", tags=["canvases"])


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _check_write(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.can_write(workspace_id, user_id):
        await _check_member(workspace_id, user_id)
        raise HTTPException(status_code=403, detail="Viewers can read but not modify canvases")


async def _ws_canvas(workspace_id: UUID, canvas_id: UUID) -> dict:
    canvas = await canvas_service.get_canvas(canvas_id)
    if not canvas or canvas["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return canvas


@ws_router.post("", response_model=CanvasResponse)
async def create_canvas(
    workspace_id: UUID,
    req: CanvasCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_write(workspace_id, current_user["id"])
    canvas = await canvas_service.create_canvas(
        workspace_id, req.title, req.blocks, current_user["id"], session_id=req.session_id
    )
    return CanvasResponse(**canvas)


@ws_router.get("", response_model=CanvasListResponse)
async def list_canvases(
    workspace_id: UUID,
    session_id: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    canvases = await canvas_service.list_canvases(workspace_id, session_id=session_id)
    return CanvasListResponse(canvases=[CanvasResponse(**c) for c in canvases])


@ws_router.patch("/{canvas_id}", response_model=CanvasResponse)
async def update_canvas(
    workspace_id: UUID,
    canvas_id: UUID,
    req: CanvasUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_write(workspace_id, current_user["id"])
    await _ws_canvas(workspace_id, canvas_id)
    canvas = await canvas_service.update_canvas(
        canvas_id, current_user["id"], title=req.title, blocks=req.blocks
    )
    return CanvasResponse(**canvas)


@ws_router.delete("/{canvas_id}")
async def delete_canvas(
    workspace_id: UUID,
    canvas_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_write(workspace_id, current_user["id"])
    await _ws_canvas(workspace_id, canvas_id)
    deleted = await canvas_service.delete_canvas(canvas_id)
    return {"deleted": deleted, "canvas_id": str(canvas_id)}


@router.get("/{canvas_id}", response_model=CanvasResponse)
async def get_canvas_by_id(
    canvas_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Any failure is a 404: an unscoped lookup must not confirm a canvas the
    caller can't read exists."""
    canvas = await canvas_service.get_canvas(canvas_id)
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")
    if not await workspace_service.is_member(canvas["workspace_id"], current_user["id"]):
        raise HTTPException(status_code=404, detail="Canvas not found")
    return CanvasResponse(**canvas)
