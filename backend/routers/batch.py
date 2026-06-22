"""Batch operations: move / soft-delete / restore many tree items at once.

Best-effort — the response reports per-item success and errors, so a partial
failure (one item the caller can't write) still applies the rest.
"""

from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import BatchMoveRequest, BatchRequest
from ..services import batch_service

router = APIRouter(prefix="/api/v1/me/batch", tags=["batch"])


def _items(req) -> list[dict]:
    return [{"object_type": i.object_type, "object_id": i.object_id} for i in req.items]


@router.post("/move")
async def batch_move(
    req: BatchMoveRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    return await batch_service.batch_move(
        owner_user_id,
        current_user["id"],
        _items(req),
        target_folder_id=req.target_folder_id,
        move_to_root=req.move_to_root,
    )


@router.post("/delete")
async def batch_delete(
    req: BatchRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    return await batch_service.batch_delete(owner_user_id, current_user["id"], _items(req))


@router.post("/restore")
async def batch_restore(
    req: BatchRequest,
    current_user: dict = Depends(get_current_user),
):
    owner_user_id = current_user["id"]
    return await batch_service.batch_restore(owner_user_id, current_user["id"], _items(req))
