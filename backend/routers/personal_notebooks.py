"""Personal notebooks router: workspace-less markdown files."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ..auth import get_current_user, get_user_from_api_key
from ..models import (
    NotebookCreateRequest,
    NotebookFolderCreateRequest,
    NotebookFolderResponse,
    NotebookFolderUpdateRequest,
    NotebookResponse,
    NotebookTreeResponse,
    NotebookUpdateRequest,
)
from ..services import notebook_service
from ..services.yjs_manager import yjs_manager as yjs_mgr

router = APIRouter(prefix="/api/v1/notebooks", tags=["personal_notebooks"])


# --- Notebook CRUD ---


@router.get("", response_model=NotebookTreeResponse)
async def list_notebooks(current_user: dict = Depends(get_current_user)):
    tree = await notebook_service.list_personal_notebook_tree(current_user["id"])
    return NotebookTreeResponse(**tree)


@router.post("", response_model=NotebookResponse, status_code=201)
async def create_notebook(
    req: NotebookCreateRequest, current_user: dict = Depends(get_current_user),
):
    try:
        nb = await notebook_service.create_personal_notebook(
            req.name, current_user["id"],
            folder_id=req.folder_id, content=req.content,
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Notebook name already exists")
        raise
    return NotebookResponse(**nb)


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    nb = await notebook_service.get_personal_notebook(notebook_id, current_user["id"])
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return NotebookResponse(**nb)


@router.patch("/{notebook_id}", response_model=NotebookResponse)
async def update_notebook(
    notebook_id: UUID, req: NotebookUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    nb = await notebook_service.update_personal_notebook(
        notebook_id, current_user["id"],
        name=req.name, folder_id=req.folder_id,
        content=req.content, move_to_root=req.move_to_root,
    )
    if not nb:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return NotebookResponse(**nb)


@router.delete("/{notebook_id}", status_code=204)
async def delete_notebook(
    notebook_id: UUID, current_user: dict = Depends(get_current_user),
):
    deleted = await notebook_service.delete_personal_notebook(notebook_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Notebook not found")


# --- Folders ---


@router.post("/folders", response_model=NotebookFolderResponse, status_code=201)
async def create_folder(
    req: NotebookFolderCreateRequest, current_user: dict = Depends(get_current_user),
):
    try:
        folder = await notebook_service.create_personal_folder(
            req.name, current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Folder name already exists")
        raise
    return NotebookFolderResponse(**folder)


@router.patch("/folders/{folder_id}", response_model=NotebookFolderResponse)
async def rename_folder(
    folder_id: UUID, req: NotebookFolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    folder = await notebook_service.rename_personal_folder(
        folder_id, current_user["id"], req.name,
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return NotebookFolderResponse(**folder)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: UUID, current_user: dict = Depends(get_current_user),
):
    deleted = await notebook_service.delete_personal_folder(folder_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")


# --- Yjs Collaborative Editing ---


@router.websocket("/{notebook_id}/yjs")
async def yjs_websocket(
    notebook_id: UUID, websocket: WebSocket, token: str = "",
):
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return
    nb = await notebook_service.get_personal_notebook(notebook_id, user["id"])
    if not nb:
        await websocket.close(code=4003, reason="Not the notebook owner")
        return

    await websocket.accept()
    await yjs_mgr.handle_ws_connect(websocket, str(notebook_id), None)
    try:
        while True:
            data = await websocket.receive_bytes()
            await yjs_mgr.handle_ws_message(websocket, str(notebook_id), data)
    except WebSocketDisconnect:
        pass
    finally:
        await yjs_mgr.handle_ws_disconnect(websocket, str(notebook_id))
