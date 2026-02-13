import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

from ..auth import get_current_user, get_user_from_api_key
from ..models import WSMessage
from ..services import message_service, room_service, webhook_service
from ..services.connection_manager import manager

router = APIRouter(tags=["realtime"])


@router.websocket("/api/v1/rooms/{room_id}/ws")
async def websocket_endpoint(room_id: UUID, websocket: WebSocket, token: str = Query(...)):
    # Auth via query param
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not await room_service.is_member(room_id, user["id"]):
        await websocket.close(code=4003, reason="Not a member")
        return

    await websocket.accept()
    manager.ws_connect(room_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                ws_msg = WSMessage(**data)
            except Exception:
                await websocket.send_text(json.dumps({"error": "Invalid message format"}))
                continue

            if ws_msg.type == "typing":
                await manager.broadcast_typing(room_id, user["name"], sender_ws=websocket)
            elif ws_msg.type == "message" and ws_msg.content:
                msg = await message_service.send_message(
                    room_id=room_id,
                    sender_id=user["id"],
                    content=ws_msg.content,
                    reply_to_id=ws_msg.reply_to_id,
                )
                event = {"type": "message", **msg}
                await manager.broadcast(room_id, event)
                asyncio.create_task(webhook_service.dispatch_webhooks(room_id, event, sender_id=user["id"]))
    except WebSocketDisconnect:
        pass
    finally:
        manager.ws_disconnect(room_id, websocket)


@router.get("/api/v1/rooms/{room_id}/stream")
async def sse_endpoint(room_id: UUID, current_user: dict = Depends(get_current_user)):
    if not await room_service.is_member(room_id, current_user["id"]):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not a member")

    queue = manager.sse_subscribe(room_id)

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            manager.sse_unsubscribe(room_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
