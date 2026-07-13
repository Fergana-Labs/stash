"""Clips router: save webpages and files from the browser extension."""

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

from ..auth import get_current_user
from ..models import UploadResponse
from ..services import clip_service
from ..services.article_extraction import ArticleExtractionError
from .files import MAX_FILE_SIZE, _page_app_url

router = APIRouter(prefix="/api/v1/me/clips", tags=["clips"])


class ClipPageRequest(BaseModel):
    url: HttpUrl
    html: str
    title: str | None = None


@router.post("/page", response_model=UploadResponse, status_code=201)
async def clip_page(
    body: ClipPageRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        page = await clip_service.save_page_clip(
            owner_user_id=current_user["id"],
            user_id=current_user["id"],
            url=str(body.url),
            html=body.html,
            title=body.title,
        )
    except ArticleExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return UploadResponse(
        kind="page",
        id=page["id"],
        owner_user_id=page["owner_user_id"],
        folder_id=page.get("folder_id"),
        name=page["name"],
        content_type=page["content_type"],
        app_url=_page_app_url(page["id"]),
        created_at=page["created_at"],
        content_markdown=page.get("content_markdown") or None,
        created_by=page["created_by"],
    )


@router.post("/file", response_model=UploadResponse, status_code=201)
async def clip_file(
    file: UploadFile,
    url: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB)")
    try:
        return await clip_service.save_file_clip(
            owner_user_id=current_user["id"],
            user_id=current_user["id"],
            url=url,
            filename=file.filename or "clip",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
