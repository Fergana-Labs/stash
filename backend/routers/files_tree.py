"""Files router: workspace-scoped folders (nested) and pages."""

import asyncio
import json
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..database import get_pool
from ..models import (
    CommentReconcileRequest,
    CommentReplyRequest,
    CommentResolveRequest,
    CommentThread,
    CommentThreadCreateRequest,
    CommentThreadListResponse,
    CopyRequest,
    FolderCreateRequest,
    FolderListResponse,
    FolderResponse,
    FolderUpdateRequest,
    PageCreateRequest,
    PageResponse,
    PageUpdateRequest,
    WorkspacePageEntry,
    WorkspacePageListResponse,
    WorkspaceTreeResponse,
)
from ..services import (
    comment_service,
    files_tree_service,
    page_events,
    permission_service,
    security_audit_service,
    workspace_service,
)
from ..services.files_tree_service import (
    DuplicateFolderName,
    DuplicatePageName,
    FolderCycle,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["files"])
canonical_router = APIRouter(prefix="/api/v1", tags=["files"])


async def _check_ws_access(workspace_id: UUID, user_id: UUID) -> None:
    """Read gate: any member (viewer/editor/owner) is allowed."""
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _check_ws_write(workspace_id: UUID, user_id: UUID) -> None:
    """Write gate: owner or editor only. Viewer is blocked."""
    if not await workspace_service.can_write(workspace_id, user_id):
        raise HTTPException(
            status_code=403,
            detail="Viewers can read but not edit this workspace",
        )


async def _check_ws_owns_folder(workspace_id: UUID, folder_id: UUID) -> dict:
    folder = await files_tree_service.get_folder(folder_id)
    if not folder or folder["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


async def _check_content_access(
    object_type: str,
    object_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    *,
    require: str = "read",
) -> None:
    allowed = await permission_service.check_access(
        object_type,
        object_id,
        user_id,
        workspace_id=workspace_id,
        require=require,
    )
    if allowed:
        return
    raise HTTPException(status_code=404, detail=f"{object_type.title()} not found")


# --- Pages: flat listing ---


@router.get("/pages", response_model=WorkspacePageListResponse)
async def list_workspace_pages(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    rows = await files_tree_service.list_workspace_pages(workspace_id, current_user["id"])
    return WorkspacePageListResponse(pages=[WorkspacePageEntry(**r) for r in rows])


# Heartbeat keeps the SSE connection (and intermediaries) alive between edits.
_PAGE_EVENTS_HEARTBEAT_S = 25


@router.get("/pages/events")
async def page_events_stream(
    workspace_id: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """SSE stream of page-update events for the workspace. Open viewers subscribe
    and refetch the affected page so an agent (or another user) editing it shows
    up live."""
    await _check_ws_access(workspace_id, current_user["id"])

    async def event_stream():
        queue = page_events.subscribe(workspace_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_PAGE_EVENTS_HEARTBEAT_S)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            page_events.unsubscribe(workspace_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Tree (nested folders + pages) ---


@router.get("/tree", response_model=WorkspaceTreeResponse)
async def get_workspace_tree(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    tree = await files_tree_service.list_workspace_tree(workspace_id, current_user["id"])
    return WorkspaceTreeResponse(**tree)


# --- Folders ---


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    folders = await files_tree_service.list_folders(workspace_id, current_user["id"])
    return FolderListResponse(folders=[FolderResponse(**f) for f in folders])


@router.post("/folders", response_model=FolderResponse, status_code=201)
async def create_folder(
    workspace_id: UUID,
    req: FolderCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if req.parent_folder_id is None:
        await _check_ws_write(workspace_id, current_user["id"])
    else:
        await _check_ws_owns_folder(workspace_id, req.parent_folder_id)
        await _check_content_access(
            "folder",
            req.parent_folder_id,
            workspace_id,
            current_user["id"],
            require="write",
        )
    try:
        folder = await files_tree_service.create_folder(
            workspace_id,
            req.name,
            current_user["id"],
            parent_folder_id=req.parent_folder_id,
        )
    except DuplicateFolderName as e:
        raise HTTPException(status_code=409, detail=str(e))
    return FolderResponse(**folder)


@router.get("/folders/{folder_id}", response_model=FolderResponse)
async def get_folder(
    workspace_id: UUID,
    folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    folder = await _check_ws_owns_folder(workspace_id, folder_id)
    await _check_content_access("folder", folder_id, workspace_id, current_user["id"])
    return FolderResponse(**folder)


@router.get("/folders/{folder_id}/contents")
async def get_folder_contents(
    workspace_id: UUID,
    folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Immediate children of a folder — subfolders, pages, files — plus
    the breadcrumb chain from workspace root down to this folder. Powers
    the unified Files tree (sidebar lazy-expand + folder detail page)."""
    folder = await _check_ws_owns_folder(workspace_id, folder_id)
    await _check_content_access("folder", folder_id, workspace_id, current_user["id"])
    pool = get_pool()

    # Breadcrumb ancestry via recursive CTE
    ancestry_rows = await pool.fetch(
        """
        WITH RECURSIVE chain AS (
          SELECT id, name, parent_folder_id, 0 AS depth
          FROM folders WHERE id = $1
          UNION ALL
          SELECT f.id, f.name, f.parent_folder_id, c.depth + 1
          FROM folders f JOIN chain c ON c.parent_folder_id = f.id
        )
        SELECT id, name FROM chain ORDER BY depth DESC
        """,
        folder_id,
    )
    breadcrumbs = [{"id": str(r["id"]), "name": r["name"]} for r in ancestry_rows]

    readable_folder = permission_service.readable_content_condition("folder", "f", 3)
    readable_page = permission_service.readable_content_condition("page", "p", 3)
    readable_file = permission_service.readable_content_condition("file", "fi", 3)
    readable_table = permission_service.readable_content_condition("table", "t", 3)
    subfolders = await pool.fetch(
        "SELECT id, name, "
        "       ("
        "         SELECT COUNT(*) FROM pages p WHERE p.folder_id = f.id "
        "         AND p.workspace_id = $2 "
        "         AND COALESCE(p.metadata->>'shared_in_cartridge_id', '') = '' "
        "         AND p.deleted_at IS NULL "
        f"         AND {readable_page}"
        "       ) AS page_count, "
        "       ("
        "         SELECT COUNT(*) FROM files fi WHERE fi.folder_id = f.id "
        "         AND fi.workspace_id = $2 "
        "         AND fi.deleted_at IS NULL "
        f"         AND {readable_file}"
        "       ) AS file_count "
        "FROM folders f WHERE f.parent_folder_id = $1 AND f.workspace_id = $2 "
        f"AND {readable_folder} "
        "ORDER BY name",
        folder_id,
        workspace_id,
        current_user["id"],
    )
    pages = await pool.fetch(
        "SELECT id, name, content_type FROM pages p WHERE p.folder_id = $1 "
        "AND p.workspace_id = $2 "
        "AND COALESCE(p.metadata->>'shared_in_cartridge_id', '') = '' "
        "AND p.deleted_at IS NULL "
        f"AND {readable_page} "
        "ORDER BY name",
        folder_id,
        workspace_id,
        current_user["id"],
    )
    files = await pool.fetch(
        "SELECT id, name, size_bytes, content_type, created_at, linked_table_id "
        "FROM files fi WHERE fi.folder_id = $1 AND fi.workspace_id = $2 "
        "AND fi.deleted_at IS NULL "
        f"AND {readable_file} "
        "ORDER BY created_at DESC",
        folder_id,
        workspace_id,
        current_user["id"],
    )
    tables = await pool.fetch(
        "SELECT id, name, "
        "(SELECT COUNT(*) FROM table_rows tr WHERE tr.table_id = t.id) AS row_count "
        "FROM tables t WHERE t.folder_id = $1 AND t.workspace_id = $2 "
        f"AND {readable_table} "
        "ORDER BY name",
        folder_id,
        workspace_id,
        current_user["id"],
    )
    subfolders = [dict(r) for r in subfolders]
    pages = [dict(r) for r in pages]
    files = [dict(r) for r in files]
    tables = [dict(r) for r in tables]

    file_payload = [
        {
            "id": str(f["id"]),
            "name": f["name"],
            "size_bytes": f["size_bytes"],
            "content_type": f["content_type"],
            "url": None,
            "created_at": f["created_at"],
            "linked_table_id": str(f["linked_table_id"]) if f["linked_table_id"] else None,
        }
        for f in files
    ]

    return {
        "folder": {
            "id": str(folder["id"]),
            "name": folder["name"],
            "parent_folder_id": (
                str(folder["parent_folder_id"]) if folder["parent_folder_id"] else None
            ),
        },
        "breadcrumbs": breadcrumbs,
        "subfolders": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "page_count": int(r["page_count"] or 0),
                "file_count": int(r["file_count"] or 0),
            }
            for r in subfolders
        ],
        "pages": [
            {"id": str(r["id"]), "name": r["name"], "content_type": r["content_type"]}
            for r in pages
        ],
        "files": file_payload,
        "tables": [
            {"id": str(r["id"]), "name": r["name"], "row_count": int(r["row_count"] or 0)}
            for r in tables
        ],
    }


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    workspace_id: UUID,
    folder_id: UUID,
    req: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_owns_folder(workspace_id, folder_id)
    await _check_content_access(
        "folder",
        folder_id,
        workspace_id,
        current_user["id"],
        require="write",
    )
    if req.parent_folder_id is not None and not req.move_to_root:
        await _check_ws_owns_folder(workspace_id, req.parent_folder_id)
        await _check_content_access(
            "folder",
            req.parent_folder_id,
            workspace_id,
            current_user["id"],
            require="write",
        )
    try:
        folder = await files_tree_service.update_folder(
            folder_id,
            workspace_id,
            name=req.name,
            parent_folder_id=req.parent_folder_id,
            move_to_root=req.move_to_root,
        )
    except DuplicateFolderName as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FolderCycle as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**folder)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    workspace_id: UUID,
    folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_owns_folder(workspace_id, folder_id)
    await _check_content_access(
        "folder",
        folder_id,
        workspace_id,
        current_user["id"],
        require="write",
    )
    deleted = await files_tree_service.delete_folder(folder_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


@router.post("/folders/{folder_id}/copy", response_model=FolderResponse, status_code=201)
async def copy_folder(
    workspace_id: UUID,
    folder_id: UUID,
    req: CopyRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_owns_folder(workspace_id, folder_id)
    await _check_content_access("folder", folder_id, workspace_id, current_user["id"])
    if req.target_folder_id is not None:
        await _check_ws_owns_folder(workspace_id, req.target_folder_id)
        await _check_content_access(
            "folder", req.target_folder_id, workspace_id, current_user["id"], require="write"
        )
    else:
        await _check_ws_write(workspace_id, current_user["id"])
    try:
        folder = await files_tree_service.copy_folder(
            folder_id, workspace_id, current_user["id"], target_parent_id=req.target_folder_id
        )
    except FolderCycle as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**folder)


# --- Pages ---


@router.post("/pages/new", response_model=PageResponse, status_code=201)
async def create_page(
    workspace_id: UUID,
    req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    if req.folder_id is None:
        await _check_ws_write(workspace_id, current_user["id"])
    else:
        await _check_ws_owns_folder(workspace_id, req.folder_id)
        await _check_content_access(
            "folder",
            req.folder_id,
            workspace_id,
            current_user["id"],
            require="write",
        )
    try:
        page = await files_tree_service.create_page(
            workspace_id,
            req.name,
            current_user["id"],
            folder_id=req.folder_id,
            content=req.content,
            content_type=req.content_type,
            content_html=req.content_html,
            html_layout=req.html_layout,
        )
    except DuplicatePageName as e:
        raise HTTPException(status_code=409, detail=str(e))
    return PageResponse(**page)


@router.post("/pages/{page_id}/copy", response_model=PageResponse, status_code=201)
async def copy_page(
    workspace_id: UUID,
    page_id: UUID,
    req: CopyRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_content_access("page", page_id, workspace_id, current_user["id"])
    if req.target_folder_id is not None:
        await _check_ws_owns_folder(workspace_id, req.target_folder_id)
        await _check_content_access(
            "folder", req.target_folder_id, workspace_id, current_user["id"], require="write"
        )
    else:
        await _check_ws_write(workspace_id, current_user["id"])
    page = await files_tree_service.copy_page(
        page_id, workspace_id, current_user["id"], target_folder_id=req.target_folder_id
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.get("/pages/semantic-search")
async def semantic_search_pages(
    workspace_id: UUID,
    q: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    from ..services import embeddings as embedding_service

    if not embedding_service.is_configured():
        raise HTTPException(status_code=503, detail="Embedding service not configured")
    query_embedding = await embedding_service.embed_text(q)
    if query_embedding is None:
        raise HTTPException(status_code=500, detail="Failed to embed query")
    pages = await files_tree_service.search_pages_vector(
        workspace_id,
        query_embedding,
        limit,
        current_user["id"],
    )
    return {"pages": pages}


@router.get("/pages/search")
async def search_pages(
    workspace_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    pages = await files_tree_service.search_pages_fts(workspace_id, q, limit, current_user["id"])
    return {"pages": pages}


@canonical_router.get("/pages/{page_id}", response_model=PageResponse)
async def get_page_by_id(
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Any failure is a 404: an unscoped lookup must not confirm that a
    page the caller can't read exists."""
    page = await files_tree_service.get_page_by_id(page_id, current_user["id"])
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.get("/pages/{page_id}", response_model=PageResponse)
async def get_page(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    # No workspace-membership pre-gate: a page may be shared with someone who
    # isn't a member (the primary collaboration path). get_page enforces
    # check_access (owner OR share OR open cartridge) and returns None otherwise.
    page = await files_tree_service.get_page(page_id, workspace_id, current_user["id"])
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.get("/pages/{page_id}/download")
async def download_page(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Raw page body, parallel to /files/{file_id}/download.

    Returns the page's markdown source (or HTML, for html-typed pages) so
    callers can export, diff, or feed it to other tools the same way they
    would a binary file. Permission is the existing page-read check —
    members of the workspace plus anyone the page is shared with.
    """
    page = await files_tree_service.get_page(page_id, workspace_id, current_user["id"])
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    is_html = (page.get("content_type") or "").lower() == "html"
    body = (page.get("content_html") if is_html else page.get("content_markdown")) or ""
    suffix = ".html" if is_html else ".md"
    media = "text/html; charset=utf-8" if is_html else "text/markdown; charset=utf-8"
    name = page.get("name") or "page"
    filename = name if name.lower().endswith(suffix) else f"{name}{suffix}"
    return Response(
        content=body,
        media_type=media,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.patch("/pages/{page_id}", response_model=PageResponse)
async def update_page(
    workspace_id: UUID,
    page_id: UUID,
    req: PageUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_content_access(
        "page",
        page_id,
        workspace_id,
        current_user["id"],
        require="write",
    )
    if req.folder_id is not None and not req.move_to_root:
        await _check_ws_owns_folder(workspace_id, req.folder_id)
        await _check_content_access(
            "folder",
            req.folder_id,
            workspace_id,
            current_user["id"],
            require="write",
        )

    try:
        page = await files_tree_service.update_page(
            page_id,
            workspace_id,
            current_user["id"],
            name=req.name,
            folder_id=req.folder_id,
            content=req.content,
            content_type=req.content_type,
            content_html=req.content_html,
            html_layout=req.html_layout,
            move_to_root=req.move_to_root,
            guard_content_hash=not (req.collab_projection and req.content is not None),
            notify=not req.collab_projection,
        )
    except DuplicatePageName as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_content_access(
        "page",
        page_id,
        workspace_id,
        current_user["id"],
        require="write",
    )
    deleted = await files_tree_service.delete_page(page_id, workspace_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")
    await security_audit_service.record_content_lifecycle_event(
        operation="deleted",
        actor_user_id=current_user["id"],
        workspace_id=workspace_id,
        target_type="page",
        target_id=page_id,
    )


@router.post("/pages/{page_id}/restore", status_code=204)
async def restore_page(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_content_access("page", page_id, workspace_id, current_user["id"], require="write")
    restored = await files_tree_service.restore_page(page_id, workspace_id)
    if not restored:
        raise HTTPException(status_code=404, detail="Page not in trash")
    await security_audit_service.record_content_lifecycle_event(
        operation="restored",
        actor_user_id=current_user["id"],
        workspace_id=workspace_id,
        target_type="page",
        target_id=page_id,
    )


@router.delete("/pages/{page_id}/purge", status_code=204)
async def purge_page(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Permanent delete — only callable on a page already in trash."""
    await _check_content_access("page", page_id, workspace_id, current_user["id"], require="write")
    purged = await files_tree_service.purge_page(page_id, workspace_id)
    if not purged:
        raise HTTPException(status_code=404, detail="Page not in trash")
    await security_audit_service.record_content_lifecycle_event(
        operation="purged",
        actor_user_id=current_user["id"],
        workspace_id=workspace_id,
        target_type="page",
        target_id=page_id,
    )


# --- Page comments ---


async def _check_page_in_workspace(workspace_id: UUID, page_id: UUID) -> None:
    pool = get_pool()
    found = await pool.fetchval(
        "SELECT 1 FROM pages WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL",
        page_id,
        workspace_id,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Page not found")


@router.get(
    "/pages/{page_id}/comments/threads",
    response_model=CommentThreadListResponse,
)
async def list_comment_threads(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_content_access("page", page_id, workspace_id, current_user["id"])
    await _check_page_in_workspace(workspace_id, page_id)
    threads = await comment_service.list_threads(page_id)
    return CommentThreadListResponse(threads=[CommentThread(**t) for t in threads])


@router.post(
    "/pages/{page_id}/comments/threads",
    response_model=CommentThread,
    status_code=201,
)
async def create_comment_thread(
    workspace_id: UUID,
    page_id: UUID,
    req: CommentThreadCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    # Commenting needs at least the 'comment' share level (workspace members
    # always qualify); a plain read-only share can view but not comment.
    await _check_content_access(
        "page", page_id, workspace_id, current_user["id"], require="comment"
    )
    await _check_page_in_workspace(workspace_id, page_id)
    thread = await comment_service.create_thread(
        page_id,
        quoted_text=req.quoted_text,
        prefix=req.prefix,
        suffix=req.suffix,
        body=req.body,
        created_by=current_user["id"],
    )
    return CommentThread(**thread)


@router.post(
    "/pages/{page_id}/comments/threads/{thread_id}/messages",
    response_model=CommentThread,
    status_code=201,
)
async def reply_to_thread(
    workspace_id: UUID,
    page_id: UUID,
    thread_id: UUID,
    req: CommentReplyRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_content_access(
        "page", page_id, workspace_id, current_user["id"], require="comment"
    )
    await _check_page_in_workspace(workspace_id, page_id)
    thread = await comment_service.add_reply(thread_id, body=req.body, author_id=current_user["id"])
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return CommentThread(**thread)


@router.patch(
    "/pages/{page_id}/comments/threads/{thread_id}",
    response_model=CommentThread,
)
async def update_thread_resolved(
    workspace_id: UUID,
    page_id: UUID,
    thread_id: UUID,
    req: CommentResolveRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_content_access("page", page_id, workspace_id, current_user["id"])
    await _check_page_in_workspace(workspace_id, page_id)
    thread = await comment_service.set_resolved(
        thread_id, resolved=req.resolved, user_id=current_user["id"]
    )
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return CommentThread(**thread)


@router.delete(
    "/pages/{page_id}/comments/threads/{thread_id}",
    status_code=204,
)
async def delete_comment_thread(
    workspace_id: UUID,
    page_id: UUID,
    thread_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Delete an entire thread. Only the thread creator is allowed."""
    await _check_content_access("page", page_id, workspace_id, current_user["id"])
    await _check_page_in_workspace(workspace_id, page_id)
    result = await comment_service.delete_thread(thread_id, user_id=current_user["id"])
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Thread not found")
    if result == "forbidden":
        raise HTTPException(status_code=403, detail="Only the thread author can delete it")


@router.delete(
    "/pages/{page_id}/comments/messages/{message_id}",
)
async def delete_comment_message(
    workspace_id: UUID,
    page_id: UUID,
    message_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Delete a single message. Author only. If the deleted message was
    the last one in its thread, the thread is auto-deleted and the
    response body's `thread` field is null — the frontend should then
    strip the inline anchor from the page content.
    """
    await _check_content_access("page", page_id, workspace_id, current_user["id"])
    await _check_page_in_workspace(workspace_id, page_id)
    status, thread = await comment_service.delete_message(message_id, user_id=current_user["id"])
    if status == "not_found":
        raise HTTPException(status_code=404, detail="Message not found")
    if status == "forbidden":
        raise HTTPException(status_code=403, detail="Only the author can delete this message")
    if status == "ok_thread_gone":
        return {"thread": None, "thread_deleted": True}
    return {"thread": CommentThread(**thread), "thread_deleted": False}


@router.post(
    "/pages/{page_id}/comments/reconcile",
    status_code=204,
)
async def reconcile_comment_anchors(
    workspace_id: UUID,
    page_id: UUID,
    req: CommentReconcileRequest,
    current_user: dict = Depends(get_current_user),
):
    """Mark threads whose inline anchor is missing as orphaned.

    The editor posts the set of `data-comment-id` values that are still
    present in the content right after each save. Threads not in the set
    flip to orphaned = true; threads in the set flip back to false.
    Resolved threads are left alone.
    """
    await _check_ws_write(workspace_id, current_user["id"])
    await _check_content_access("page", page_id, workspace_id, current_user["id"], require="write")
    await _check_page_in_workspace(workspace_id, page_id)
    await comment_service.reconcile_orphans(page_id, req.present_ids)
