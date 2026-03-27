"""Personal rooms router: workspace-less chat rooms."""

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
)
from ..services import chat_service
from ..services.connection_manager import manager

router = APIRouter(prefix="/api/v1/rooms", tags=["personal_rooms"])


async def _check_room_access(chat_id: UUID, user_id: UUID) -> None:
    """Verify user owns this personal room."""
    if not await chat_service.is_personal_chat_owner(chat_id, user_id):
        raise HTTPException(status_code=403, detail="Not the owner of this room")


@router.post("", response_model=ChatResponse, status_code=201)
async def create_room(
    req: ChatCreateRequest, current_user: dict = Depends(get_current_user),
):
    chat = await chat_service.create_personal_chat(
        req.name, req.description, current_user["id"],
    )
    return ChatResponse(**chat)


@router.get("", response_model=ChatListResponse)
async def list_rooms(current_user: dict = Depends(get_current_user)):
    chats = await chat_service.list_personal_chats(current_user["id"])
    return ChatListResponse(chats=[ChatResponse(**c) for c in chats])


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_room(
    chat_id: UUID, current_user: dict = Depends(get_current_user),
):
    await _check_room_access(chat_id, current_user["id"])
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Room not found")
    return ChatResponse(**chat)


@router.delete("/{chat_id}", status_code=204)
async def delete_room(
    chat_id: UUID, current_user: dict = Depends(get_current_user),
):
    deleted = await chat_service.delete_personal_chat(chat_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Room not found")


# --- Messages ---


@router.post("/{chat_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    chat_id: UUID, req: ChatMessageSendRequest,
    current_user: dict = Depends(get_current_user),
):
    await _check_room_access(chat_id, current_user["id"])
    msg = await chat_service.send_message(
        chat_id, current_user["id"], req.content, reply_to_id=req.reply_to_id,
    )
    await manager.broadcast(chat_id, {"type": "message", **msg})
    return ChatMessageResponse(**msg)


@router.get("/{chat_id}/messages", response_model=ChatMessageListResponse)
async def get_messages(
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


@router.get("/{chat_id}/messages/search", response_model=ChatMessageListResponse)
async def search_messages(
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


@router.websocket("/{chat_id}/ws")
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
