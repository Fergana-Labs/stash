import asyncio
import json
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # room_id -> set of WebSocket connections
        self._ws_connections: dict[UUID, set[WebSocket]] = {}
        # room_id -> set of asyncio.Queue for SSE subscribers
        self._sse_queues: dict[UUID, set[asyncio.Queue]] = {}

    def ws_connect(self, room_id: UUID, ws: WebSocket):
        if room_id not in self._ws_connections:
            self._ws_connections[room_id] = set()
        self._ws_connections[room_id].add(ws)

    def ws_disconnect(self, room_id: UUID, ws: WebSocket):
        if room_id in self._ws_connections:
            self._ws_connections[room_id].discard(ws)
            if not self._ws_connections[room_id]:
                del self._ws_connections[room_id]

    def sse_subscribe(self, room_id: UUID) -> asyncio.Queue:
        if room_id not in self._sse_queues:
            self._sse_queues[room_id] = set()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._sse_queues[room_id].add(queue)
        return queue

    def sse_unsubscribe(self, room_id: UUID, queue: asyncio.Queue):
        if room_id in self._sse_queues:
            self._sse_queues[room_id].discard(queue)
            if not self._sse_queues[room_id]:
                del self._sse_queues[room_id]

    async def broadcast(self, room_id: UUID, message: dict):
        """Broadcast a message to all WS + SSE subscribers in a room."""
        data = json.dumps(message, default=str)

        # Send to WebSocket clients
        if room_id in self._ws_connections:
            dead = []
            for ws in self._ws_connections[room_id]:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._ws_connections[room_id].discard(ws)

        # Send to SSE subscribers
        if room_id in self._sse_queues:
            dead_queues = []
            for queue in self._sse_queues[room_id]:
                try:
                    queue.put_nowait(data)
                except asyncio.QueueFull:
                    dead_queues.append(queue)
            for q in dead_queues:
                self._sse_queues[room_id].discard(q)

    async def ping_all(self):
        """Send a ping to every WebSocket; remove any that fail."""
        total_removed = 0
        for room_id in list(self._ws_connections.keys()):
            conns = self._ws_connections.get(room_id)
            if not conns:
                continue
            dead = []
            for ws in list(conns):
                try:
                    await ws.send_text('{"type":"ping"}')
                except Exception:
                    dead.append(ws)
            for ws in dead:
                conns.discard(ws)
            total_removed += len(dead)
            if not conns:
                del self._ws_connections[room_id]
        if total_removed:
            import logging
            logging.getLogger("moltchat").info(
                f"ping_all: removed {total_removed} dead connection(s)"
            )

    async def broadcast_typing(self, room_id: UUID, user_name: str, sender_ws: WebSocket | None = None):
        """Broadcast typing indicator, excluding the sender."""
        data = json.dumps({"type": "typing", "user": user_name})
        if room_id in self._ws_connections:
            dead = []
            for ws in self._ws_connections[room_id]:
                if ws is sender_ws:
                    continue
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._ws_connections[room_id].discard(ws)


manager = ConnectionManager()
