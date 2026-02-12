from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..models import MessageListResponse, MessageResponse, MessageSendRequest
from ..services import message_service, room_service
from ..services.connection_manager import manager

router = APIRouter(prefix="/api/v1/rooms/{room_id}/messages", tags=["messages"])


@router.post("", response_model=MessageResponse, status_code=201)
async def send_message(
    room_id: UUID,
    req: MessageSendRequest,
    current_user: dict = Depends(get_current_user),
):
    if not await room_service.is_member(room_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this room")
    msg = await message_service.send_message(
        room_id=room_id,
        sender_id=current_user["id"],
        content=req.content,
        reply_to_id=req.reply_to_id,
    )
    # Broadcast to real-time subscribers
    await manager.broadcast(room_id, {"type": "message", **msg})
    return MessageResponse(**msg)


@router.get("", response_model=MessageListResponse)
async def get_messages(
    room_id: UUID,
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    if not await room_service.is_member(room_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this room")
    messages, has_more = await message_service.get_messages(
        room_id=room_id, after=after, before=before, limit=limit
    )
    return MessageListResponse(
        messages=[MessageResponse(**m) for m in messages],
        has_more=has_more,
    )
