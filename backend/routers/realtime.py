"""Real-time router: WebSocket and SSE for workspace chats."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

from ..auth import get_current_user, get_user_from_api_key
from ..models import WSMessage
from ..services import chat_service, permission_service, workspace_service, webhook_service
from ..services.connection_manager import manager

router = APIRouter(tags=["realtime"])


@router.websocket("/api/v1/workspaces/{workspace_id}/chats/{chat_id}/ws")
async def chat_websocket(
    workspace_id: UUID, chat_id: UUID, websocket: WebSocket, token: str = Query(...),
):
    """WebSocket for real-time chat messaging within a workspace."""
    user = await get_user_from_api_key(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    has_access = await permission_service.check_access(
        "chat", chat_id, user["id"], workspace_id=workspace_id,
    )
    if not has_access:
        await websocket.close(code=4003, reason="No access to this chat")
        return

    await websocket.accept()
    manager.ws_connect(chat_id, websocket)

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
                await manager.broadcast_typing(chat_id, user["name"], sender_ws=websocket)
            elif ws_msg.type == "message" and ws_msg.content:
                msg = await chat_service.send_message(
                    chat_id=chat_id,
                    sender_id=user["id"],
                    content=ws_msg.content,
                    reply_to_id=ws_msg.reply_to_id,
                )
                event = {"type": "message", **msg}
                await manager.broadcast(chat_id, event)
                asyncio.create_task(
                    webhook_service.dispatch_webhooks(
                        workspace_id, "chat.message", event, sender_id=user["id"],
                    )
                )
    except WebSocketDisconnect:
        pass
    finally:
        manager.ws_disconnect(chat_id, websocket)


@router.get("/api/v1/workspaces/{workspace_id}/chats/{chat_id}/stream")
async def chat_sse(
    workspace_id: UUID, chat_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Server-Sent Events for real-time chat streaming."""
    has_access = await permission_service.check_access(
        "chat", chat_id, current_user["id"], workspace_id=workspace_id,
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="No access to this chat")

    queue = manager.sse_subscribe(chat_id)

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            manager.sse_unsubscribe(chat_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
