"""Chat router: workspace chats and personal rooms."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..auth import get_current_user, get_user_from_api_key
from ..models import (
    ChatCreateRequest,
    ChatListResponse,
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatMessageSendRequest,
    ChatResponse,
    PermissionResponse,
    SetVisibilityRequest,
    ShareRequest,
    ShareResponse,
)
from ..services import chat_service, permission_service, watch_service, workspace_service, webhook_service
from ..services.connection_manager import manager

ws_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/chats", tags=["chats"])
personal_router = APIRouter(prefix="/api/v1/rooms", tags=["personal_rooms"])


# --- Shared auth helpers ---


async def _check_member(workspace_id: UUID, user_id: UUID) -> None:
    if not await workspace_service.is_member(workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a workspace member")


async def _check_chat_access(workspace_id: UUID, chat_id: UUID, user_id: UUID) -> None:
    has_access = await permission_service.check_access(
        "chat", chat_id, user_id, workspace_id=workspace_id,
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="No access to this chat")


async def _check_room_access(chat_id: UUID, user_id: UUID) -> None:
    """Verify user owns this personal room."""
    if not await chat_service.is_personal_chat_owner(chat_id, user_id):
        raise HTTPException(status_code=403, detail="Not the owner of this room")


# ===== Workspace chat endpoints =====


@ws_router.post("", response_model=ChatResponse, status_code=201)
async def create_chat(
    workspace_id: UUID, req: ChatCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    chat = await chat_service.create_chat(
        workspace_id, req.name, req.description, current_user["id"],
    )
    return ChatResponse(**chat)


@ws_router.get("", response_model=ChatListResponse)
async def list_chats(
    workspace_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    chats = await chat_service.list_chats(workspace_id)
    return ChatListResponse(chats=[ChatResponse(**c) for c in chats])


@ws_router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    workspace_id: UUID, chat_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_chat_access(workspace_id, chat_id, current_user["id"])
    chat = await chat_service.get_chat(chat_id)
    if not chat or chat.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatResponse(**chat)


@ws_router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    workspace_id: UUID, chat_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can delete chats")
    deleted = await chat_service.delete_chat(chat_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")


@ws_router.post("/{chat_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    workspace_id: UUID, chat_id: UUID, req: ChatMessageSendRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_chat_access(workspace_id, chat_id, current_user["id"])
    attachments = [a.model_dump(mode="json") for a in req.attachments] if req.attachments else None
    msg = await chat_service.send_message(
        chat_id, current_user["id"], req.content, reply_to_id=req.reply_to_id,
        attachments=attachments,
    )
    await manager.broadcast(chat_id, {"type": "message", **msg})
    asyncio.create_task(
        webhook_service.dispatch_webhooks(
            workspace_id, "chat.message", msg, sender_id=current_user["id"],
        )
    )
    asyncio.create_task(watch_service.auto_mark_read(current_user["id"], chat_id))
    return ChatMessageResponse(**msg)


@ws_router.get("/{chat_id}/messages", response_model=ChatMessageListResponse)
async def get_messages(
    workspace_id: UUID, chat_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    after: str | None = Query(None),
    before: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _check_chat_access(workspace_id, chat_id, current_user["id"])
    messages, has_more = await chat_service.get_messages(
        chat_id, limit=limit, after=after, before=before,
    )
    return ChatMessageListResponse(
        messages=[ChatMessageResponse(**m) for m in messages],
        has_more=has_more,
    )


@ws_router.get("/{chat_id}/messages/search", response_model=ChatMessageListResponse)
async def search_ws_messages(
    workspace_id: UUID, chat_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    await _check_chat_access(workspace_id, chat_id, current_user["id"])
    messages = await chat_service.search_messages(chat_id, q, limit=limit)
    return ChatMessageListResponse(
        messages=[ChatMessageResponse(**m) for m in messages],
        has_more=False,
    )


# --- Workspace permissions ---


@ws_router.get("/{chat_id}/permissions", response_model=PermissionResponse)
async def get_permissions(
    workspace_id: UUID, chat_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    await _check_member(workspace_id, current_user["id"])
    perms = await permission_service.get_permissions("chat", chat_id)
    return PermissionResponse(**perms)


@ws_router.patch("/{chat_id}/permissions")
async def set_visibility(
    workspace_id: UUID, chat_id: UUID, req: SetVisibilityRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can change visibility")
    await permission_service.set_visibility("chat", chat_id, req.visibility)
    return {"status": "ok", "visibility": req.visibility}


@ws_router.post("/{chat_id}/permissions/share", response_model=ShareResponse)
async def add_share(
    workspace_id: UUID, chat_id: UUID, req: ShareRequest,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can share")
    share = await permission_service.add_share(
        "chat", chat_id, req.user_id, req.permission, current_user["id"],
    )
    from ..database import get_pool
    pool = get_pool()
    user = await pool.fetchrow("SELECT name FROM users WHERE id = $1", req.user_id)
    return ShareResponse(
        user_id=share["user_id"], user_name=user["name"] if user else "",
        permission=share["permission"], granted_by=share["granted_by"],
        created_at=share["created_at"],
    )


@ws_router.delete("/{chat_id}/permissions/share/{user_id}", status_code=204)
async def remove_share(
    workspace_id: UUID, chat_id: UUID, user_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    role = await workspace_service.get_member_role(workspace_id, current_user["id"])
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can remove shares")
    await permission_service.remove_share("chat", chat_id, user_id)


# ===== Personal room endpoints =====


@personal_router.post("", response_model=ChatResponse, status_code=201)
async def create_room(
    req: ChatCreateRequest, current_user: dict = Depends(get_current_user),
):
    chat = await chat_service.create_chat(
        None, req.name, req.description, current_user["id"],
    )
    return ChatResponse(**chat)


@personal_router.get("", response_model=ChatListResponse)
async def list_rooms(current_user: dict = Depends(get_current_user)):
    chats = await chat_service.list_chats(None, user_id=current_user["id"])
    return ChatListResponse(chats=[ChatResponse(**c) for c in chats])


@personal_router.get("/{chat_id}", response_model=ChatResponse)
async def get_room(
    chat_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_room_access(chat_id, current_user["id"])
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Room not found")
    return ChatResponse(**chat)


@personal_router.delete("/{chat_id}", status_code=204)
async def delete_room(
    chat_id: UUID, current_user: dict = Depends(get_current_user),
):
    deleted = await chat_service.delete_chat(chat_id, None, user_id=current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Room not found")


@personal_router.post("/{chat_id}/messages", response_model=ChatMessageResponse)
async def send_room_message(
    chat_id: UUID, req: ChatMessageSendRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_room_access(chat_id, current_user["id"])
    attachments = [a.model_dump(mode="json") for a in req.attachments] if req.attachments else None
    msg = await chat_service.send_message(
        chat_id, current_user["id"], req.content, reply_to_id=req.reply_to_id,
        attachments=attachments,
    )
    await manager.broadcast(chat_id, {"type": "message", **msg})
    asyncio.create_task(watch_service.auto_mark_read(current_user["id"], chat_id))
    return ChatMessageResponse(**msg)


@personal_router.get("/{chat_id}/messages", response_model=ChatMessageListResponse)
async def get_room_messages(
    chat_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    after: str | None = Query(None),
    before: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _check_room_access(chat_id, current_user["id"])
    messages, has_more = await chat_service.get_messages(
        chat_id, limit=limit, after=after, before=before,
    )
    return ChatMessageListResponse(
        messages=[ChatMessageResponse(**m) for m in messages],
        has_more=has_more,
    )


@personal_router.get("/{chat_id}/messages/search", response_model=ChatMessageListResponse)
async def search_room_messages(
    chat_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    await _check_room_access(chat_id, current_user["id"])
    messages = await chat_service.search_messages(chat_id, q, limit=limit)
    return ChatMessageListResponse(
        messages=[ChatMessageResponse(**m) for m in messages],
        has_more=False,
    )


@personal_router.websocket("/{chat_id}/ws")
async def room_websocket(chat_id: UUID, websocket: WebSocket, token: str = ""):
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return
    if not await chat_service.is_personal_chat_owner(chat_id, user["id"]):
        await websocket.close(code=4003, reason="Not the room owner")
        return

    await websocket.accept()
    manager.ws_connect(chat_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "message" and data.get("content"):
                msg = await chat_service.send_message(
                    chat_id, user["id"], data["content"],
                    reply_to_id=data.get("reply_to_id"),
                )
                await manager.broadcast(chat_id, {"type": "message", **msg})
            elif data.get("type") == "typing":
                await manager.broadcast_typing(chat_id, user["name"], sender_ws=websocket)
    except WebSocketDisconnect:
        pass
    finally:
        manager.ws_disconnect(chat_id, websocket)
