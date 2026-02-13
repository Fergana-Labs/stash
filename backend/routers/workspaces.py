from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..auth import get_current_user, get_user_from_api_key
from ..models import (
    WorkspaceFileCreateRequest,
    WorkspaceFileResponse,
    WorkspaceFileTreeResponse,
    WorkspaceFileUpdateRequest,
    WorkspaceFolderCreateRequest,
    WorkspaceFolderResponse,
    WorkspaceFolderUpdateRequest,
)
from ..services import room_service, workspace_service
from ..services.yjs_manager import yjs_manager

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


async def _check_workspace_membership(workspace_id: UUID, user_id: UUID):
    """Verify the room exists, is a workspace, and user is a member."""
    room = await room_service.get_room(workspace_id)
    if not room:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if room.get("type", "chat") != "workspace":
        raise HTTPException(status_code=400, detail="Room is not a workspace")
    if not await room_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return room


# --- File Tree ---

@router.get("/{workspace_id}/files", response_model=WorkspaceFileTreeResponse)
async def list_files(workspace_id: UUID, current_user: dict = Depends(get_current_user)):
    await _check_workspace_membership(workspace_id, current_user["id"])
    tree = await workspace_service.list_file_tree(workspace_id)
    return tree


# --- Files ---

@router.post("/{workspace_id}/files", response_model=WorkspaceFileResponse, status_code=201)
async def create_file(
    workspace_id: UUID,
    req: WorkspaceFileCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_membership(workspace_id, current_user["id"])
    if req.folder_id:
        folder = await workspace_service.get_folder(req.folder_id, workspace_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
    try:
        f = await workspace_service.create_file(
            workspace_id=workspace_id,
            name=req.name,
            created_by=current_user["id"],
            folder_id=req.folder_id,
            content=req.content,
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="A file with that name already exists in this location")
        raise
    return WorkspaceFileResponse(**f)


@router.get("/{workspace_id}/files/{file_id}", response_model=WorkspaceFileResponse)
async def get_file(
    workspace_id: UUID, file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_membership(workspace_id, current_user["id"])
    f = await workspace_service.get_file(file_id, workspace_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return WorkspaceFileResponse(**{k: v for k, v in f.items() if k != "yjs_state"})


@router.patch("/{workspace_id}/files/{file_id}", response_model=WorkspaceFileResponse)
async def update_file(
    workspace_id: UUID, file_id: UUID,
    req: WorkspaceFileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_membership(workspace_id, current_user["id"])

    existing = await workspace_service.get_file(file_id, workspace_id)
    if not existing:
        raise HTTPException(status_code=404, detail="File not found")

    if req.folder_id:
        folder = await workspace_service.get_folder(req.folder_id, workspace_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

    # If content is being updated, route through Yjs manager for real-time sync
    if req.content is not None:
        await yjs_manager.apply_rest_update(file_id, workspace_id, req.content)

    try:
        f = await workspace_service.update_file(
            file_id=file_id,
            workspace_id=workspace_id,
            updated_by=current_user["id"],
            name=req.name,
            folder_id=req.folder_id,
            content=req.content,
            move_to_root=req.move_to_root,
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="A file with that name already exists in this location")
        raise

    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return WorkspaceFileResponse(**f)


@router.delete("/{workspace_id}/files/{file_id}")
async def delete_file(
    workspace_id: UUID, file_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_membership(workspace_id, current_user["id"])
    deleted = await workspace_service.delete_file(file_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"ok": True}


# --- Folders ---

@router.post("/{workspace_id}/folders", response_model=WorkspaceFolderResponse, status_code=201)
async def create_folder(
    workspace_id: UUID,
    req: WorkspaceFolderCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_membership(workspace_id, current_user["id"])
    try:
        folder = await workspace_service.create_folder(
            workspace_id=workspace_id,
            name=req.name,
            created_by=current_user["id"],
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="A folder with that name already exists")
        raise
    return WorkspaceFolderResponse(**folder)


@router.patch("/{workspace_id}/folders/{folder_id}", response_model=WorkspaceFolderResponse)
async def rename_folder(
    workspace_id: UUID, folder_id: UUID,
    req: WorkspaceFolderUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_membership(workspace_id, current_user["id"])
    try:
        folder = await workspace_service.rename_folder(folder_id, workspace_id, req.name)
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="A folder with that name already exists")
        raise
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return WorkspaceFolderResponse(**folder)


@router.delete("/{workspace_id}/folders/{folder_id}")
async def delete_folder(
    workspace_id: UUID, folder_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_workspace_membership(workspace_id, current_user["id"])
    deleted = await workspace_service.delete_folder(folder_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


# --- Yjs WebSocket ---

@router.websocket("/{workspace_id}/files/{file_id}/yjs")
async def yjs_websocket(
    workspace_id: UUID, file_id: UUID,
    websocket: WebSocket, token: str = Query(...),
):
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not await room_service.is_member(workspace_id, user["id"]):
        await websocket.close(code=4003, reason="Not a member")
        return

    # Verify workspace and file exist
    room = await room_service.get_room(workspace_id)
    if not room or room.get("type", "chat") != "workspace":
        await websocket.close(code=4004, reason="Not a workspace")
        return

    f = await workspace_service.get_file(file_id, workspace_id)
    if not f:
        await websocket.close(code=4004, reason="File not found")
        return

    await websocket.accept()
    await yjs_manager.handle_ws_connect(websocket, file_id, workspace_id)

    try:
        while True:
            data = await websocket.receive_bytes()
            await yjs_manager.handle_ws_message(websocket, file_id, data)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await yjs_manager.handle_ws_disconnect(websocket, file_id)
