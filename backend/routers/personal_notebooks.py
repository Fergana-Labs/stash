"""Personal notebooks router: workspace-less notebook collections."""

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
)
from ..services import notebook_service
from ..services.yjs_manager import yjs_manager as yjs_mgr

router = APIRouter(prefix="/api/v1/notebooks", tags=["personal_notebooks"])


async def _check_notebook_owner(notebook_id: UUID, user_id: UUID) -> dict:
    nb = await notebook_service.get_notebook(notebook_id)
    if not nb or nb.get("workspace_id") is not None or nb.get("created_by") != user_id:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return nb


# --- Notebook (collection) CRUD ---


@router.post("", response_model=NotebookResponse, status_code=201)
async def create_notebook(
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


@router.get("", response_model=NotebookListResponse)
async def list_notebooks(current_user: dict = Depends(get_current_user)):
    nbs = await notebook_service.list_personal_notebooks(current_user["id"])
    return NotebookListResponse(notebooks=[NotebookResponse(**n) for n in nbs])


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    nb = await _check_notebook_owner(notebook_id, current_user["id"])
    return NotebookResponse(**nb)


@router.delete("/{notebook_id}", status_code=204)
async def delete_notebook(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    await notebook_service.delete_notebook(notebook_id)


# --- Pages ---


@router.get("/{notebook_id}/pages", response_model=PageTreeResponse)
async def list_pages(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    tree = await notebook_service.list_page_tree(notebook_id)
    return PageTreeResponse(**tree)


@router.post("/{notebook_id}/pages", response_model=PageResponse, status_code=201)
async def create_page(
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


@router.get("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def get_page(
    notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    page = await notebook_service.get_page(page_id, notebook_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(**page)


@router.patch("/{notebook_id}/pages/{page_id}", response_model=PageResponse)
async def update_page(
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


@router.delete("/{notebook_id}/pages/{page_id}", status_code=204)
async def delete_page(
    notebook_id: UUID, page_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    deleted = await notebook_service.delete_page(page_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")


# --- Folders ---


@router.post("/{notebook_id}/folders", response_model=FolderResponse, status_code=201)
async def create_folder(
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


@router.patch("/{notebook_id}/folders/{folder_id}", response_model=FolderResponse)
async def rename_folder(
    notebook_id: UUID, folder_id: UUID, req: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    folder = await notebook_service.rename_folder(folder_id, notebook_id, req.name)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**folder)


@router.delete("/{notebook_id}/folders/{folder_id}", status_code=204)
async def delete_folder(
    notebook_id: UUID, folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_notebook_owner(notebook_id, current_user["id"])
    deleted = await notebook_service.delete_folder(folder_id, notebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


# --- Yjs ---


@router.websocket("/{notebook_id}/pages/{page_id}/yjs")
async def yjs_websocket(
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
