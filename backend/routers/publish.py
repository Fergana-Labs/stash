"""One-call publish endpoint for AI agents."""

from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..config import settings
from ..models import PublishRequest, PublishResponse
from ..services import files_tree_service, shared_skill_service, user_scope_service

router = APIRouter(prefix="/api/v1", tags=["publish"])


@router.post("/publish", response_model=PublishResponse)
async def publish(
    req: PublishRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a skill folder containing the content page and publish it."""
    if req.owner_user_id is None:
        owner_user_id = await user_scope_service.scope_id_for_user(current_user["id"])
        if owner_user_id is None:
            raise HTTPException(
                status_code=400,
                detail="No primary scope; pass owner_user_id explicitly",
            )
    else:
        owner_user_id = req.owner_user_id
        if not await user_scope_service.is_member(owner_user_id, current_user["id"]):
            raise HTTPException(status_code=403, detail="Not a scope member")

    if not await user_scope_service.can_write(owner_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Viewers can read but not publish")

    # Gate before any side effects: publish_folder would reject non-owners
    # anyway, but only after the folder and page were already created.
    if not await user_scope_service.is_owner(owner_user_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Only scope owners can publish Skills")

    if req.folder_id is not None:
        folder = await files_tree_service.get_folder(req.folder_id)
        if not folder or folder["owner_user_id"] != owner_user_id:
            raise HTTPException(status_code=404, detail="Folder not found in this scope")
        target_folder = folder
    else:
        # Each publish mints its own skill folder (folder_id is unique per
        # publish record), named after the title with " (N)" dedupe.
        name = req.title
        n = 2
        while True:
            try:
                target_folder = await files_tree_service.create_folder(
                    owner_user_id, name, current_user["id"]
                )
                break
            except files_tree_service.DuplicateFolderName:
                name = f"{req.title} ({n})"
                n += 1

    page = await files_tree_service.create_page(
        owner_user_id=owner_user_id,
        name=req.title,
        created_by=current_user["id"],
        folder_id=target_folder["id"],
        content=req.content if req.content_type == "markdown" else "",
        content_type=req.content_type,
        content_html=req.content if req.content_type == "html" else "",
        html_layout=req.html_layout,
    )

    try:
        skill = await shared_skill_service.publish_folder(
            owner_user_id,
            current_user["id"],
            target_folder["id"],
            title=req.title,
        )
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    base = settings.PUBLIC_URL.rstrip("/")
    return PublishResponse(
        page_id=page["id"],
        folder_id=target_folder["id"],
        owner_user_id=owner_user_id,
        url=f"{base}/skills/{skill['slug']}",
        skill_id=skill["id"],
        skill_slug=skill["slug"],
    )
