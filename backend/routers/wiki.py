"""Wiki router: workspace-scoped folders (nested) and pages.

Replaces the old notebook router. Folders sit directly under the workspace,
nest via parent_folder_id, and pages live either at the workspace root or
inside a folder.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..database import get_pool
from ..models import (
    FolderCreateRequest,
    FolderListResponse,
    FolderResponse,
    FolderUpdateRequest,
    PageCreateRequest,
    PageResponse,
    PageUpdateRequest,
    PermissionResponse,
    SetVisibilityRequest,
    ShareRequest,
    ShareResponse,
    WorkspacePageEntry,
    WorkspacePageListResponse,
    WorkspaceTreeResponse,
)
from ..services import permission_service, storage_service, wiki_service, workspace_service
from ..services.wiki_service import (
    DuplicateFolderName,
    DuplicatePageName,
    FolderCycle,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["wiki"])


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
    folder = await wiki_service.get_folder(folder_id)
    if not folder or folder["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


# --- Pages: flat listing for wiki-link autocomplete ---


@router.get("/pages", response_model=WorkspacePageListResponse)
async def list_workspace_pages(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    rows = await wiki_service.list_workspace_pages(workspace_id)
    return WorkspacePageListResponse(pages=[WorkspacePageEntry(**r) for r in rows])


# --- Tree (nested folders + pages) ---


@router.get("/tree", response_model=WorkspaceTreeResponse)
async def get_workspace_tree(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    tree = await wiki_service.list_workspace_tree(workspace_id)
    return WorkspaceTreeResponse(**tree)


# --- Folders ---


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    folders = await wiki_service.list_folders(workspace_id)
    return FolderListResponse(folders=[FolderResponse(**f) for f in folders])


@router.post("/folders", response_model=FolderResponse, status_code=201)
async def create_folder(
    workspace_id: UUID,
    req: FolderCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_write(workspace_id, current_user["id"])
    if req.parent_folder_id is not None:
        await _check_ws_owns_folder(workspace_id, req.parent_folder_id)
    try:
        folder = await wiki_service.create_folder(
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
    await _check_ws_access(workspace_id, current_user["id"])
    folder = await _check_ws_owns_folder(workspace_id, folder_id)
    return FolderResponse(**folder)


@router.get("/folders/{folder_id}/contents")
async def get_folder_contents(
    workspace_id: UUID,
    folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Immediate children of a folder — subfolders, pages, files — plus
    the breadcrumb chain from workspace root down to this folder. Powers
    the unified Wiki tree (sidebar lazy-expand + folder detail page)."""
    await _check_ws_access(workspace_id, current_user["id"])
    folder = await _check_ws_owns_folder(workspace_id, folder_id)
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

    subfolders = await pool.fetch(
        "SELECT id, name, "
        "       (SELECT COUNT(*) FROM pages p WHERE p.folder_id = f.id) AS page_count, "
        "       (SELECT COUNT(*) FROM files fi WHERE fi.folder_id = f.id) AS file_count "
        "FROM folders f WHERE f.parent_folder_id = $1 ORDER BY name",
        folder_id,
    )
    pages = await pool.fetch(
        "SELECT id, name FROM pages WHERE folder_id = $1 ORDER BY name",
        folder_id,
    )
    files = await pool.fetch(
        "SELECT id, name, size_bytes, content_type, storage_key, created_at, linked_table_id "
        "FROM files WHERE folder_id = $1 ORDER BY created_at DESC",
        folder_id,
    )

    file_payload = []
    for f in files:
        try:
            url = await storage_service.get_file_url(f["storage_key"])
        except Exception:
            url = None
        file_payload.append(
            {
                "id": str(f["id"]),
                "name": f["name"],
                "size_bytes": f["size_bytes"],
                "content_type": f["content_type"],
                "url": url,
                "created_at": f["created_at"],
                "linked_table_id": str(f["linked_table_id"]) if f["linked_table_id"] else None,
            }
        )

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
        "pages": [{"id": str(r["id"]), "name": r["name"]} for r in pages],
        "files": file_payload,
    }


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    workspace_id: UUID,
    folder_id: UUID,
    req: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_write(workspace_id, current_user["id"])
    await _check_ws_owns_folder(workspace_id, folder_id)
    if req.parent_folder_id is not None and not req.move_to_root:
        await _check_ws_owns_folder(workspace_id, req.parent_folder_id)
    try:
        folder = await wiki_service.update_folder(
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
    await _check_ws_write(workspace_id, current_user["id"])
    deleted = await wiki_service.delete_folder(folder_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


# --- Pages ---


@router.post("/pages/new", response_model=PageResponse, status_code=201)
async def create_page(
    workspace_id: UUID,
    req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_write(workspace_id, current_user["id"])
    if req.folder_id is not None:
        await _check_ws_owns_folder(workspace_id, req.folder_id)
    try:
        page = await wiki_service.create_page(
            workspace_id,
            req.name,
            current_user["id"],
            folder_id=req.folder_id,
            content=req.content,
            content_type=req.content_type,
            content_html=req.content_html,
        )
    except DuplicatePageName as e:
        raise HTTPException(status_code=409, detail=str(e))
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
    pages = await wiki_service.search_pages_vector(workspace_id, query_embedding, limit)
    return {"pages": pages}


@router.get("/pages/search")
async def search_pages(
    workspace_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    pages = await wiki_service.search_pages_fts(workspace_id, q, limit)
    return {"pages": pages}


@router.get("/pages/{page_id}", response_model=PageResponse)
async def get_page(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    page = await wiki_service.get_page(page_id, workspace_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.patch("/pages/{page_id}", response_model=PageResponse)
async def update_page(
    workspace_id: UUID,
    page_id: UUID,
    req: PageUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_write(workspace_id, current_user["id"])
    if req.folder_id is not None and not req.move_to_root:
        await _check_ws_owns_folder(workspace_id, req.folder_id)
    try:
        page = await wiki_service.update_page(
            page_id,
            workspace_id,
            current_user["id"],
            name=req.name,
            folder_id=req.folder_id,
            content=req.content,
            content_type=req.content_type,
            content_html=req.content_html,
            move_to_root=req.move_to_root,
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
    await _check_ws_write(workspace_id, current_user["id"])
    deleted = await wiki_service.delete_page(page_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")


# --- Wiki features (backlinks, page graph) ---


@router.get("/pages/{page_id}/backlinks")
async def get_page_backlinks(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    links = await wiki_service.get_backlinks(page_id)
    return {"backlinks": links}


@router.get("/pages/{page_id}/outlinks")
async def get_page_outlinks(
    workspace_id: UUID,
    page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    links = await wiki_service.get_outlinks(page_id)
    return {"outlinks": links}


@router.get("/graph")
async def get_workspace_graph(
    workspace_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    return await wiki_service.get_workspace_graph(workspace_id)


# --- Folder permissions / sharing ---


@router.get("/folders/{folder_id}/permissions", response_model=PermissionResponse)
async def get_folder_permissions(
    workspace_id: UUID,
    folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_owns_folder(workspace_id, folder_id)
    perms = await permission_service.get_permissions("folder", folder_id)
    return PermissionResponse(**perms)


@router.patch("/folders/{folder_id}/permissions")
async def set_folder_visibility(
    workspace_id: UUID,
    folder_id: UUID,
    req: SetVisibilityRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can change visibility")
    await _check_ws_owns_folder(workspace_id, folder_id)
    await permission_service.set_visibility("folder", folder_id, req.visibility)
    return {"status": "ok", "visibility": req.visibility}


@router.post("/folders/{folder_id}/permissions/share", response_model=ShareResponse)
async def add_folder_share(
    workspace_id: UUID,
    folder_id: UUID,
    req: ShareRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can share")
    await _check_ws_owns_folder(workspace_id, folder_id)
    share = await permission_service.add_share(
        "folder",
        folder_id,
        req.user_id,
        req.permission,
        current_user["id"],
    )
    from ..database import get_pool

    pool = get_pool()
    user = await pool.fetchrow("SELECT name FROM users WHERE id = $1", req.user_id)
    return ShareResponse(
        user_id=share["user_id"],
        user_name=user["name"] if user else "",
        permission=share["permission"],
        granted_by=share["granted_by"],
        created_at=share["created_at"],
    )


@router.delete("/folders/{folder_id}/permissions/share/{user_id}", status_code=204)
async def remove_folder_share(
    workspace_id: UUID,
    folder_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can remove shares")
    await _check_ws_owns_folder(workspace_id, folder_id)
    await permission_service.remove_share("folder", folder_id, user_id)
