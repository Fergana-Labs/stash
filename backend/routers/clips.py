"""Clips router: save webpages and files from the browser extension."""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

from ..auth import get_current_user
from ..models import UploadResponse
from ..services import clip_router, clip_service, url_import_service
from ..services.article_extraction import ArticleExtractionError
from .files import MAX_FILE_SIZE, _page_app_url

router = APIRouter(prefix="/api/v1/me/clips", tags=["clips"])


class ClipPageRequest(BaseModel):
    url: HttpUrl
    html: str
    title: str | None = None


@router.post("/page", response_model=None, status_code=201)
async def clip_page(
    body: ClipPageRequest,
    current_user: dict = Depends(get_current_user),
):
    """Save a clipped page. Returns 201 + the created page, except for URLs
    whose content isn't in the posted DOM (YouTube, arXiv abstracts) — those
    become async import jobs and return 202 + the import id."""
    url = str(body.url)
    if clip_router.is_async_url(url):
        from ..tasks.clips import dispatch_url_imports

        ids = await url_import_service.create_url_imports(
            owner_user_id=current_user["id"],
            created_by=current_user["id"],
            items=[{"url": url, "title": body.title}],
        )
        dispatch_url_imports(ids)
        return JSONResponse(status_code=202, content={"import_id": str(ids[0])})
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


@router.get("/{import_id}")
async def get_clip_import(
    import_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    row = await url_import_service.get_url_import(import_id, current_user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return {
        "id": str(row["id"]),
        "url": row["url"],
        "status": row["status"],
        "error": row["error"],
        "result_page_id": str(row["result_page_id"]) if row["result_page_id"] else None,
        "result_file_id": str(row["result_file_id"]) if row["result_file_id"] else None,
    }
