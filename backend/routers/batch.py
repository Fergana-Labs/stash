"""Batch operations: move / soft-delete / restore many tree items at once.

Best-effort — the response reports per-item success and errors, so a partial
failure (one item the caller can't write) still applies the rest.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..models import BatchMoveRequest, BatchRequest
from ..services import batch_service, user_scope_service

router = APIRouter(prefix="/api/v1/workspaces/{owner_user_id}/batch", tags=["batch"])


async def _check_member(owner_user_id: UUID, user_id: UUID) -> None:
    if not await user_scope_service.is_member(owner_user_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


def _items(req) -> list[dict]:
    return [{"object_type": i.object_type, "object_id": i.object_id} for i in req.items]


@router.post("/move")
async def batch_move(
    owner_user_id: UUID,
    req: BatchMoveRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(owner_user_id, current_user["id"])
    return await batch_service.batch_move(
        owner_user_id,
        current_user["id"],
        _items(req),
        target_folder_id=req.target_folder_id,
        move_to_root=req.move_to_root,
    )


@router.post("/delete")
async def batch_delete(
    owner_user_id: UUID,
    req: BatchRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(owner_user_id, current_user["id"])
    return await batch_service.batch_delete(owner_user_id, current_user["id"], _items(req))


@router.post("/restore")
async def batch_restore(
    owner_user_id: UUID,
    req: BatchRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(owner_user_id, current_user["id"])
    return await batch_service.batch_restore(owner_user_id, current_user["id"], _items(req))
