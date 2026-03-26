"""DM router: workspace-less direct messages between two users."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from ..auth import get_current_user, get_user_from_api_key
from ..models import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatMessageSendRequest,
    DMCreateRequest,
    DMListResponse,
    DMResponse,
    UserSearchResult,
)
from ..services import chat_service, dm_service
from ..services.connection_manager import manager

router = APIRouter(prefix="/api/v1/dms", tags=["dms"])


@router.post("", response_model=DMResponse, status_code=200)
async def create_or_get_dm(
    req: DMCreateRequest, current_user: dict = Depends(get_current_user),
):
    """Start or get a DM conversation. Idempotent."""
    target_user_id = req.user_id

    if target_user_id is None and req.username:
        from ..database import get_pool
        pool = get_pool()
        row = await pool.fetchrow("SELECT id FROM users WHERE name = $1", req.username)
        if not row:
            raise HTTPException(status_code=404, detail=f"User '{req.username}' not found")
        target_user_id = row["id"]

    if target_user_id is None:
        raise HTTPException(status_code=400, detail="Provide either user_id or username")

    try:
        dm = await dm_service.get_or_create_dm(current_user["id"], target_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return dm


@router.get("", response_model=DMListResponse)
async def list_dms(current_user: dict = Depends(get_current_user)):
    """List all DM conversations."""
    dms = await dm_service.list_dms(current_user["id"])
    return {"dms": dms}


@router.post("/{chat_id}/messages", response_model=ChatMessageResponse)
async def send_dm_message(
    chat_id: UUID, req: ChatMessageSendRequest,
    current_user: dict = Depends(get_current_user),
):
    """Send a message in a DM."""
    if not await dm_service.is_dm_participant(chat_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a participant in this DM")
    msg = await chat_service.send_message(
        chat_id, current_user["id"], req.content, reply_to_id=req.reply_to_id,
    )
    await manager.broadcast(chat_id, {"type": "message", **msg})
    return ChatMessageResponse(**msg)


@router.get("/{chat_id}/messages", response_model=ChatMessageListResponse)
async def get_dm_messages(
    chat_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    after: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Get messages in a DM."""
    if not await dm_service.is_dm_participant(chat_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a participant in this DM")
    messages, has_more = await chat_service.get_messages(chat_id, limit=limit, after=after)
    return ChatMessageListResponse(
        messages=[ChatMessageResponse(**m) for m in messages],
        has_more=has_more,
    )


@router.websocket("/{chat_id}/ws")
async def dm_websocket(chat_id: UUID, websocket: WebSocket, token: str = ""):
    """WebSocket for DM real-time messaging."""
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return
    if not await dm_service.is_dm_participant(chat_id, user["id"]):
        await websocket.close(code=4003, reason="Not a DM participant")
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


@router.get("/users/search", response_model=list[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=1, max_length=64),
    current_user: dict = Depends(get_current_user),
):
    """Search for users by name."""
    results = await dm_service.find_users(q, current_user["id"])
    return results
