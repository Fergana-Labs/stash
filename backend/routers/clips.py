"""Clips router: save webpages and files from the browser extension,
plus bulk imports (bookmarks.html, clip-all-tabs)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

from ..auth import get_current_user
from ..models import UploadResponse
from ..services import bookmarks_parser, clip_router, clip_service, url_import_service
from ..services.article_extraction import ArticleExtractionError
from .files import MAX_FILE_SIZE, _page_app_url

router = APIRouter(prefix="/api/v1/me/clips", tags=["clips"])
imports_router = APIRouter(prefix="/api/v1/me/imports", tags=["clips"])

MAX_IMPORT_URLS = 100_000
MAX_TAB_URLS = 200


class ClipPageRequest(BaseModel):
    url: HttpUrl
    # The extension runs Mozilla Readability and sends the readable article as
    # HTML (images kept, links absolute), so the server stores it as-is.
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
        await dispatch_url_imports(ids)
        return JSONResponse(status_code=202, content={"import_id": str(ids[0])})
    try:
        page = await clip_service.store_html_clip(
            owner_user_id=current_user["id"],
            user_id=current_user["id"],
            url=str(body.url),
            title=body.title or "",
            html=body.html,
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


# ===== Bulk imports =====


async def _create_import(
    *,
    owner_user_id: UUID,
    kind: str,
    filename: str | None,
    items: list[dict],
) -> JSONResponse:
    """Shared tail of both import endpoints: drop URLs this owner already
    imported (re-importing a bookmarks file must not re-clip the library),
    then batch row, url_imports rows, and a top-up of the windowed
    dispatcher — the Beat sweep drains the rest."""
    from ..tasks.clips import top_up_url_imports

    known = await url_import_service.existing_urls(owner_user_id, [item["url"] for item in items])
    new_items = [item for item in items if item["url"] not in known]
    skipped = len(items) - len(new_items)

    batch_id = await url_import_service.create_batch(
        owner_user_id=owner_user_id,
        kind=kind,
        filename=filename,
        total=len(new_items),
    )
    if new_items:
        await url_import_service.create_url_imports(
            owner_user_id=owner_user_id,
            created_by=owner_user_id,
            items=new_items,
            batch_id=batch_id,
        )
        await top_up_url_imports()
    return JSONResponse(
        status_code=201,
        content={"import_id": str(batch_id), "total": len(new_items), "skipped": skipped},
    )


@imports_router.post("/bookmarks")
async def import_bookmarks(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    """Import a Netscape-format bookmarks.html export. Every URL is fetched
    out-of-band, stored in Clips/raw, and indexed in the Bookmarks table."""
    owner_user_id = current_user["id"]
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB)")

    bookmarks = bookmarks_parser.parse_bookmarks(content.decode("utf-8", errors="replace"))
    if not bookmarks:
        raise HTTPException(status_code=400, detail="No bookmarks found in file")
    if len(bookmarks) > MAX_IMPORT_URLS:
        raise HTTPException(
            status_code=413,
            detail=f"Import has {len(bookmarks)} bookmarks (max {MAX_IMPORT_URLS})",
        )

    items = [{"url": b["url"], "title": b["title"]} for b in bookmarks]
    return await _create_import(
        owner_user_id=owner_user_id,
        kind="bookmarks",
        filename=file.filename,
        items=items,
    )


class TabsImportRequest(BaseModel):
    urls: list[HttpUrl]


@imports_router.post("/tabs")
async def import_tabs(
    body: TabsImportRequest,
    current_user: dict = Depends(get_current_user),
):
    """Save every open tab: URLs are fetched out-of-band, stored in Clips/raw,
    and indexed in the Bookmarks table."""
    owner_user_id = current_user["id"]
    if not body.urls:
        raise HTTPException(status_code=400, detail="No URLs given")
    if len(body.urls) > MAX_TAB_URLS:
        raise HTTPException(
            status_code=413, detail=f"Too many tabs ({len(body.urls)}, max {MAX_TAB_URLS})"
        )

    seen: set[str] = set()
    items = []
    for url in body.urls:
        url_str = str(url)
        if url_str in seen:
            continue
        seen.add(url_str)
        items.append({"url": url_str})
    return await _create_import(
        owner_user_id=owner_user_id,
        kind="tabs",
        filename=None,
        items=items,
    )


# ===== Extension-fed hydration =====
# URLs the server can't fetch (login walls, IP blocks) are marked
# needs_client; the extension polls this queue, refetches them with the
# user's own browser session, and posts the raw HTML back. Registered
# before /{batch_id} so "client-queue" isn't parsed as a batch id.


class ClientResultRequest(BaseModel):
    # Exactly one of html (the client-fetched page) or error (why the
    # client couldn't fetch it either) must be set.
    html: str | None = None
    title: str | None = None
    error: str | None = None


@imports_router.get("/client-queue")
async def client_queue(
    limit: int = 5,
    current_user: dict = Depends(get_current_user),
):
    """Claim up to `limit` needs_client rows for this user's extension."""
    rows = await url_import_service.claim_client_batch(current_user["id"], limit=min(limit, 20))
    return {"items": [{"id": str(r["id"]), "url": r["url"]} for r in rows]}


@imports_router.post("/{import_id}/client-result")
async def client_result(
    import_id: UUID,
    body: ClientResultRequest,
    current_user: dict = Depends(get_current_user),
):
    """Resolve a needs_client row with the extension's fetch result. The
    client is the last resort, so its failure is terminal: the bookmark is
    saved link-only rather than bounced back to the server."""
    from ..tasks.clips import _resolve_link_only

    row = await url_import_service.get_url_import(import_id, current_user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="Import not found")
    if row["status"] != "needs_client":
        raise HTTPException(status_code=409, detail=f"Import is {row['status']}")
    if (body.html is None) == (body.error is None):
        raise HTTPException(status_code=422, detail="Send exactly one of html or error")

    if body.error is not None:
        await _resolve_link_only(row, f"{row['error']}; client fetch failed: {body.error}")
        return {"status": "link_only"}

    if len(body.html.encode()) > clip_router.MAX_FETCH_BYTES:
        raise HTTPException(status_code=413, detail="HTML larger than 20 MB")
    try:
        page = await clip_service.save_page_clip(
            owner_user_id=row["owner_user_id"],
            user_id=row["created_by"],
            url=row["url"],
            html=body.html,
            title=body.title or row.get("title"),
            folder_id=row["folder_id"],
        )
    except ArticleExtractionError as e:
        await _resolve_link_only(row, f"{row['error']}; client HTML unusable: {e}")
        return {"status": "link_only"}
    await url_import_service.mark_done(import_id, page_id=page["id"])
    return {"status": "done"}


@imports_router.get("")
async def list_import_progress(
    current_user: dict = Depends(get_current_user),
):
    """Recent import batches with their progress, newest first — the app-side
    progress surface for bulk imports that grind for days. Additive: the
    extension keeps using the per-batch endpoint below."""
    batches = await url_import_service.list_batches_progress(current_user["id"])
    return {"batches": batches}


@imports_router.get("/{batch_id}")
async def get_import_progress(
    batch_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    progress = await url_import_service.batch_progress(batch_id, current_user["id"])
    if progress is None:
        raise HTTPException(status_code=404, detail="Import not found")
    progress["id"] = str(progress["id"])
    progress["created_at"] = progress["created_at"].isoformat()
    return progress
