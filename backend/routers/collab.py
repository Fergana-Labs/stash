"""Collaboration auth endpoints used by the Yjs sidecar."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..services import files_tree_service, permission_service, workspace_service

router = APIRouter(prefix="/api/v1/collab", tags=["collaboration"])


class CollabAuthorizeRequest(BaseModel):
    document_name: str = Field(..., min_length=1, max_length=256)


class CollabUser(BaseModel):
    id: UUID
    name: str
    display_name: str


class CollabAuthorizeResponse(BaseModel):
    user: CollabUser
    can_write: bool


def _parse_page_document_name(document_name: str) -> tuple[UUID, UUID]:
    parts = document_name.split(":")
    if len(parts) != 4 or parts[0] != "workspace" or parts[2] != "page":
        raise HTTPException(status_code=400, detail="Unsupported collaboration document")
    try:
        return UUID(parts[1]), UUID(parts[3])
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid collaboration document") from e


@router.post("/authorize", response_model=CollabAuthorizeResponse)
async def authorize_collab_document(
    req: CollabAuthorizeRequest,
    current_user: dict = Depends(get_current_user),
):
    workspace_id, page_id = _parse_page_document_name(req.document_name)
    if not await workspace_service.is_member(workspace_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a workspace member")

    page = await files_tree_service.get_page(page_id, workspace_id, current_user["id"])
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if page["content_type"] != "markdown":
        raise HTTPException(status_code=400, detail="Only markdown pages support live editing")

    can_write = await permission_service.check_access(
        "page",
        page_id,
        current_user["id"],
        workspace_id=workspace_id,
        require="write",
    )
    return CollabAuthorizeResponse(
        user=CollabUser(
            id=current_user["id"],
            name=current_user["name"],
            display_name=current_user["display_name"],
        ),
        can_write=can_write,
    )
