"""One-call publish endpoint for AI agents."""

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..config import settings
from ..models import PublishRequest, PublishResponse, SkillItem
from ..services import files_tree_service, shared_skill_service, workspace_service

router = APIRouter(prefix="/api/v1", tags=["publish"])

AI_DRAFTS_FOLDER_NAME = "AI Drafts"


@router.post("/publish", response_model=PublishResponse)
async def publish(
    req: PublishRequest,
    current_user: dict = Depends(get_current_user),
):
    if req.workspace_id is None:
        workspace_id = await workspace_service.get_primary_for_user(current_user["id"])
        if workspace_id is None:
            raise HTTPException(
                status_code=400,
                detail="No primary workspace; pass workspace_id explicitly",
            )
    else:
        workspace_id = req.workspace_id
        if not await workspace_service.is_member(workspace_id, current_user["id"]):
            raise HTTPException(status_code=403, detail="Not a workspace member")

    if req.folder_id is not None:
        folder = await files_tree_service.get_folder(req.folder_id)
        if not folder or folder["workspace_id"] != workspace_id:
            raise HTTPException(status_code=404, detail="Folder not found in this workspace")
        target_folder = folder
    else:
        target_folder = await files_tree_service.find_or_create_root_folder(
            workspace_id, AI_DRAFTS_FOLDER_NAME, current_user["id"]
        )

    page = await files_tree_service.create_page(
        workspace_id=workspace_id,
        name=req.title,
        created_by=current_user["id"],
        folder_id=target_folder["id"],
        content=req.content if req.content_type == "markdown" else "",
        content_type=req.content_type,
        content_html=req.content if req.content_type == "html" else "",
        html_layout=req.html_layout,
    )

    try:
        skill = await shared_skill_service.create_skill(
            workspace_id=workspace_id,
            owner_id=current_user["id"],
            title=req.title,
            description="",
            workspace_permission=req.workspace_permission,
            public_permission=req.public_permission,
            discoverable=False,
            cover_image_url=None,
            items=[SkillItem(object_type="page", object_id=page["id"], position=0)],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    base = settings.PUBLIC_URL.rstrip("/")
    return PublishResponse(
        page_id=page["id"],
        folder_id=target_folder["id"],
        workspace_id=workspace_id,
        visibility=skill["access"],
        workspace_permission=skill["workspace_permission"],
        public_permission=skill["public_permission"],
        url=f"{base}/skills/{skill['slug']}",
        skill_id=skill["id"],
        skill_slug=skill["slug"],
    )
