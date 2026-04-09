"""Notebook router: workspace and personal collection + page/folder CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ..auth import get_current_user, get_user_from_api_key
from ..models import (
    FolderCreateRequest,
    FolderResponse,
    FolderUpdateRequest,
    NotebookCreateRequest,
    NotebookListResponse,
    NotebookResponse,
    PageCreateRequest,
    PageResponse,
    PageTreeResponse,
    PageUpdateRequest,
    PermissionResponse,
    SetVisibilityRequest,
    ShareRequest,
    ShareResponse,
)
from ..services import notebook_service, permission_service, workspace_service
from ..services.yjs_manager import yjs_manager as yjs_mgr

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/notebooks", tags=["notebooks"])
personal_router = APIRouter(prefix="/api/v1/notebooks", tags=["personal_notebooks"])


# --- Shared auth helpers ---


async def _check_ws_access(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _check_ws_notebook(workspace_id: UUID, notebook_id: UUID) -> dict:
    """Verify notebook exists and belongs to the given workspace."""
    nb = await notebook_service.get_notebook(notebook_id)
    if not nb or nb.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return nb


async def _check_notebook_owner(notebook_id: UUID, user_id: UUID) -> dict:
    nb = await notebook_service.get_notebook(notebook_id)
    if not nb or nb.get("workspace_id") is not None or nb.get("created_by") != user_id:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return nb


# ===== Workspace notebook endpoints =====


@ws_router.post("", response_model=NotebookResponse, status_code=201)
async def create_ws_notebook(
    workspace_id: UUID, req: NotebookCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    try:
        nb = await notebook_service.create_notebook(
            workspace_id, req.name, req.description, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Notebook name already exists")
        raise
    return NotebookResponse(**nb)


@ws_router.get("", response_model=NotebookListResponse)
async def list_ws_notebooks(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    nbs = await notebook_service.list_notebooks(workspace_id)
    return NotebookListResponse(notebooks=[NotebookResponse(**n) for n in nbs])


@ws_router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_ws_notebook(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    nb = await _check_ws_notebook(workspace_id, notebook_id)
    return NotebookResponse(**nb)


@ws_router.delete("/{notebook_id}", status_code=204)
async def delete_ws_notebook(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    await notebook_service.delete_notebook(notebook_id)


@ws_router.get("/{notebook_id}/pages", response_model=PageTreeResponse)
async def list_ws_pages(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    tree = await notebook_service.list_page_tree(notebook_id)
    return PageTreeResponse(**tree)


@ws_router.post("/{notebook_id}/pages", response_model=PageResponse, status_code=201)
async def create_ws_page(
    workspace_id: UUID, notebook_id: UUID, req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    try:
        page = await notebook_service.create_page(
            notebook_id, req.name, current_user["id"],
            folder_id=req.folder_id, content=req.content,
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Page name already exists")
        raise
    return PageResponse(**page)


@ws_router.get("/{notebook_id}/pages/semantic-search")
async def semantic_search_ws_pages(
    workspace_id: UUID, notebook_id: UUID,
    q: str, limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Semantic search on notebook pages using embeddings."""
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    from ..services import embedding_service
    if not embedding_service.is_configured():
        raise HTTPException(status_code=503, detail="Embedding service not configured")
    query_embedding = await embedding_service.embed_text(q)
    if query_embedding is None:
        raise HTTPException(status_code=500, detail="Failed to embed query")
    pages = await notebook_service.search_pages_vector(notebook_id, query_embedding, limit)
    return {"pages": pages}


@ws_router.get("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def get_ws_page(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    page = await notebook_service.get_page(page_id, notebook_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@ws_router.patch("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def update_ws_page(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID, req: PageUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    page = await notebook_service.update_page(
        page_id, notebook_id, current_user["id"],
        name=req.name, folder_id=req.folder_id,
        content=req.content, move_to_root=req.move_to_root,
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@ws_router.delete("/{notebook_id}/pages/{page_id}", status_code=204)
async def delete_ws_page(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    deleted = await notebook_service.delete_page(page_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")


# --- Wiki features (backlinks, page graph, semantic search, auto-index) ---


@ws_router.get("/{notebook_id}/pages/{page_id}/backlinks")
async def get_ws_backlinks(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Get pages that link to this page via [[wiki links]]."""
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    links = await notebook_service.get_backlinks(page_id)
    return {"backlinks": links}


@ws_router.get("/{notebook_id}/pages/{page_id}/outlinks")
async def get_ws_outlinks(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Get pages that this page links to via [[wiki links]]."""
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    links = await notebook_service.get_outlinks(page_id)
    return {"outlinks": links}


@ws_router.get("/{notebook_id}/graph")
async def get_ws_page_graph(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Get the full wiki link graph for a notebook (nodes + edges)."""
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    return await notebook_service.get_page_graph(notebook_id)


@ws_router.post("/{notebook_id}/auto-index")
async def auto_index_ws_notebook(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Generate or update an _index page listing all pages with backlink counts."""
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    page = await notebook_service.auto_index_notebook(notebook_id, current_user["id"])
    return PageResponse(**page)


@ws_router.post("/{notebook_id}/folders", response_model=FolderResponse, status_code=201)
async def create_ws_folder(
    workspace_id: UUID, notebook_id: UUID, req: FolderCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    try:
        folder = await notebook_service.create_folder(
            notebook_id, req.name, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Folder name already exists")
        raise
    return FolderResponse(**folder)


@ws_router.patch("/{notebook_id}/folders/{folder_id}", response_model=FolderResponse)
async def rename_ws_folder(
    workspace_id: UUID, notebook_id: UUID, folder_id: UUID, req: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    folder = await notebook_service.rename_folder(folder_id, notebook_id, req.name)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**folder)


@ws_router.delete("/{notebook_id}/folders/{folder_id}", status_code=204)
async def delete_ws_folder(
    workspace_id: UUID, notebook_id: UUID, folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    deleted = await notebook_service.delete_folder(folder_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


@ws_router.websocket("/{notebook_id}/pages/{page_id}/yjs")
async def ws_yjs_websocket(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID,
    websocket: WebSocket, token: str = "",
):
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return
    if not await workspace_service.is_member(workspace_id, user["id"]):
        await websocket.close(code=4003, reason="Not a workspace member")
        return
    nb = await notebook_service.get_notebook(notebook_id)
    if not nb or nb.get("workspace_id") != workspace_id:
        await websocket.close(code=4004, reason="Notebook not found")
        return

    await websocket.accept()
    await yjs_mgr.handle_ws_connect(websocket, str(page_id), str(notebook_id))
    try:
        while True:
            data = await websocket.receive_bytes()
            await yjs_mgr.handle_ws_message(websocket, str(page_id), data)
    except WebSocketDisconnect:
        pass
    finally:
        await yjs_mgr.handle_ws_disconnect(websocket, str(page_id))


# --- Workspace permissions ---


@ws_router.get("/{notebook_id}/permissions", response_model=PermissionResponse)
async def get_permissions(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_ws_access(workspace_id, current_user["id"])
    await _check_ws_notebook(workspace_id, notebook_id)
    perms = await permission_service.get_permissions("notebook", notebook_id)
    return PermissionResponse(**perms)


@ws_router.patch("/{notebook_id}/permissions")
async def set_visibility(
    workspace_id: UUID, notebook_id: UUID, req: SetVisibilityRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can change visibility")
    await _check_ws_notebook(workspace_id, notebook_id)
    await permission_service.set_visibility("notebook", notebook_id, req.visibility)
    return {"status": "ok", "visibility": req.visibility}


@ws_router.post("/{notebook_id}/permissions/share", response_model=ShareResponse)
async def add_share(
    workspace_id: UUID, notebook_id: UUID, req: ShareRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can share")
    await _check_ws_notebook(workspace_id, notebook_id)
    share = await permission_service.add_share(
        "notebook", notebook_id, req.user_id, req.permission, current_user["id"],
    )
    from ..database import get_pool
    pool = get_pool()
    user = await pool.fetchrow("SELECT name FROM users WHERE id = $1", req.user_id)
    return ShareResponse(
        user_id=share["user_id"], user_name=user["name"] if user else "",
        permission=share["permission"], granted_by=share["granted_by"],
        created_at=share["created_at"],
    )


@ws_router.delete("/{notebook_id}/permissions/share/{user_id}", status_code=204)
async def remove_share(
    workspace_id: UUID, notebook_id: UUID, user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can remove shares")
    await _check_ws_notebook(workspace_id, notebook_id)
    await permission_service.remove_share("notebook", notebook_id, user_id)


# ===== Personal notebook endpoints =====


@personal_router.post("", response_model=NotebookResponse, status_code=201)
async def create_personal_notebook(
    req: NotebookCreateRequest, current_user: dict = Depends(get_current_user),
):
    try:
        nb = await notebook_service.create_notebook(
            None, req.name, req.description, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Notebook name already exists")
        raise
    return NotebookResponse(**nb)


@personal_router.get("", response_model=NotebookListResponse)
async def list_personal_notebooks(current_user: dict = Depends(get_current_user)):
    nbs = await notebook_service.list_notebooks(None, user_id=current_user["id"])
    return NotebookListResponse(notebooks=[NotebookResponse(**n) for n in nbs])


@personal_router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_personal_notebook(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    nb = await _check_notebook_owner(notebook_id, current_user["id"])
    return NotebookResponse(**nb)


@personal_router.delete("/{notebook_id}", status_code=204)
async def delete_personal_notebook(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    await notebook_service.delete_notebook(notebook_id)


@personal_router.get("/{notebook_id}/pages", response_model=PageTreeResponse)
async def list_personal_pages(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    tree = await notebook_service.list_page_tree(notebook_id)
    return PageTreeResponse(**tree)


@personal_router.post("/{notebook_id}/pages", response_model=PageResponse, status_code=201)
async def create_personal_page(
    notebook_id: UUID, req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    try:
        page = await notebook_service.create_page(
            notebook_id, req.name, current_user["id"],
            folder_id=req.folder_id, content=req.content,
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Page name already exists")
        raise
    return PageResponse(**page)


@personal_router.get("/{notebook_id}/pages/semantic-search")
async def semantic_search_personal_pages(
    notebook_id: UUID, q: str, limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    from ..services import embedding_service
    if not embedding_service.is_configured():
        raise HTTPException(status_code=503, detail="Embedding service not configured")
    query_embedding = await embedding_service.embed_text(q)
    if query_embedding is None:
        raise HTTPException(status_code=500, detail="Failed to embed query")
    pages = await notebook_service.search_pages_vector(notebook_id, query_embedding, limit)
    return {"pages": pages}


@personal_router.get("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def get_personal_page(
    notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    page = await notebook_service.get_page(page_id, notebook_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@personal_router.patch("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def update_personal_page(
    notebook_id: UUID, page_id: UUID, req: PageUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    page = await notebook_service.update_page(
        page_id, notebook_id, current_user["id"],
        name=req.name, folder_id=req.folder_id,
        content=req.content, move_to_root=req.move_to_root,
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@personal_router.delete("/{notebook_id}/pages/{page_id}", status_code=204)
async def delete_personal_page(
    notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    deleted = await notebook_service.delete_page(page_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")


# --- Personal wiki features ---


@personal_router.get("/{notebook_id}/pages/{page_id}/backlinks")
async def get_personal_backlinks(
    notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    links = await notebook_service.get_backlinks(page_id)
    return {"backlinks": links}


@personal_router.get("/{notebook_id}/pages/{page_id}/outlinks")
async def get_personal_outlinks(
    notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    links = await notebook_service.get_outlinks(page_id)
    return {"outlinks": links}


@personal_router.get("/{notebook_id}/graph")
async def get_personal_page_graph(
    notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    return await notebook_service.get_page_graph(notebook_id)


@personal_router.post("/{notebook_id}/auto-index")
async def auto_index_personal_notebook(
    notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    page = await notebook_service.auto_index_notebook(notebook_id, current_user["id"])
    return PageResponse(**page)


@personal_router.post("/{notebook_id}/folders", response_model=FolderResponse, status_code=201)
async def create_personal_folder(
    notebook_id: UUID, req: FolderCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    try:
        folder = await notebook_service.create_folder(
            notebook_id, req.name, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Folder name already exists")
        raise
    return FolderResponse(**folder)


@personal_router.patch("/{notebook_id}/folders/{folder_id}", response_model=FolderResponse)
async def rename_personal_folder(
    notebook_id: UUID, folder_id: UUID, req: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    folder = await notebook_service.rename_folder(folder_id, notebook_id, req.name)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**folder)


@personal_router.delete("/{notebook_id}/folders/{folder_id}", status_code=204)
async def delete_personal_folder(
    notebook_id: UUID, folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    deleted = await notebook_service.delete_folder(folder_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


@personal_router.websocket("/{notebook_id}/pages/{page_id}/yjs")
async def personal_yjs_websocket(
    notebook_id: UUID, page_id: UUID, websocket: WebSocket, token: str = "",
):
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return
    nb = await notebook_service.get_notebook(notebook_id)
    if not nb or (nb.get("workspace_id") is not None) or (nb.get("created_by") != user["id"]):
        await websocket.close(code=4003, reason="Not the notebook owner")
        return

    await websocket.accept()
    await yjs_mgr.handle_ws_connect(websocket, str(page_id), str(notebook_id))
    try:
        while True:
            data = await websocket.receive_bytes()
            await yjs_mgr.handle_ws_message(websocket, str(page_id), data)
    except WebSocketDisconnect:
        pass
    finally:
        await yjs_mgr.handle_ws_disconnect(websocket, str(page_id))
