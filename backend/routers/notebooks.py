"""Notebook router: collection + page/folder CRUD within workspaces."""

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

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/notebooks", tags=["notebooks"])


async def _check_access(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


# --- Notebook (collection) CRUD ---


@router.post("", response_model=NotebookResponse, status_code=201)
async def create_notebook(
    workspace_id: UUID, req: NotebookCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    try:
        nb = await notebook_service.create_notebook(
            workspace_id, req.name, req.description, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Notebook name already exists")
        raise
    return NotebookResponse(**nb)


@router.get("", response_model=NotebookListResponse)
async def list_notebooks(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    nbs = await notebook_service.list_notebooks(workspace_id)
    return NotebookListResponse(notebooks=[NotebookResponse(**n) for n in nbs])


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    nb = await notebook_service.get_notebook(notebook_id)
    if not nb or nb.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return NotebookResponse(**nb)


@router.delete("/{notebook_id}", status_code=204)
async def delete_notebook(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    nb = await notebook_service.get_notebook(notebook_id)
    if not nb or nb.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Notebook not found")
    await notebook_service.delete_notebook(notebook_id)


# --- Pages (within a notebook) ---


@router.get("/{notebook_id}/pages", response_model=PageTreeResponse)
async def list_pages(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    tree = await notebook_service.list_page_tree(notebook_id)
    return PageTreeResponse(**tree)


@router.post("/{notebook_id}/pages", response_model=PageResponse, status_code=201)
async def create_page(
    workspace_id: UUID, notebook_id: UUID, req: PageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
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


@router.get("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def get_page(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    page = await notebook_service.get_page(page_id, notebook_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.patch("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def update_page(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID, req: PageUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    page = await notebook_service.update_page(
        page_id, notebook_id, current_user["id"],
        name=req.name, folder_id=req.folder_id,
        content=req.content, move_to_root=req.move_to_root,
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.delete("/{notebook_id}/pages/{page_id}", status_code=204)
async def delete_page(
    workspace_id: UUID, notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    deleted = await notebook_service.delete_page(page_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")


# --- Folders (within a notebook) ---


@router.post("/{notebook_id}/folders", response_model=FolderResponse, status_code=201)
async def create_folder(
    workspace_id: UUID, notebook_id: UUID, req: FolderCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    try:
        folder = await notebook_service.create_folder(
            notebook_id, req.name, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Folder name already exists")
        raise
    return FolderResponse(**folder)


@router.patch("/{notebook_id}/folders/{folder_id}", response_model=FolderResponse)
async def rename_folder(
    workspace_id: UUID, notebook_id: UUID, folder_id: UUID, req: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    folder = await notebook_service.rename_folder(folder_id, notebook_id, req.name)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**folder)


@router.delete("/{notebook_id}/folders/{folder_id}", status_code=204)
async def delete_folder(
    workspace_id: UUID, notebook_id: UUID, folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    deleted = await notebook_service.delete_folder(folder_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


# --- Yjs Collaborative Editing ---


@router.websocket("/{notebook_id}/pages/{page_id}/yjs")
async def yjs_websocket(
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


# --- Permissions ---


@router.get("/{notebook_id}/permissions", response_model=PermissionResponse)
async def get_permissions(
    workspace_id: UUID, notebook_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_access(workspace_id, current_user["id"])
    perms = await permission_service.get_permissions("notebook", notebook_id)
    return PermissionResponse(**perms)


@router.patch("/{notebook_id}/permissions")
async def set_visibility(
    workspace_id: UUID, notebook_id: UUID, req: SetVisibilityRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can change visibility")
    await permission_service.set_visibility("notebook", notebook_id, req.visibility)
    return {"status": "ok", "visibility": req.visibility}


@router.post("/{notebook_id}/permissions/share", response_model=ShareResponse)
async def add_share(
    workspace_id: UUID, notebook_id: UUID, req: ShareRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can share")
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


@router.delete("/{notebook_id}/permissions/share/{user_id}", status_code=204)
async def remove_share(
    workspace_id: UUID, notebook_id: UUID, user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can remove shares")
    await permission_service.remove_share("notebook", notebook_id, user_id)
