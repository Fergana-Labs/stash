"""WebSocket + SSE connection manager.

broadcast() sends via Postgres NOTIFY so every process receives the message
and delivers it to its local subscribers, enabling horizontal scaling without
Redis.  Each process also holds a dedicated asyncpg connection that LISTENs on
the 'octopus_events' channel (wired up in main.py lifespan).

broadcast_local() delivers only to in-process connections; it is called by the
LISTEN callback and must NOT re-issue a NOTIFY (would cause an infinite loop).
"""

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

    # --- Connection lifecycle ---

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

    # --- Local delivery (in-process only) ---

    async def broadcast_local(self, room_id: UUID, message: dict):
        """Deliver a message to all in-process subscribers for room_id."""
        data = json.dumps(message, default=str)

        if room_id in self._ws_connections:
            dead = []
            for ws in list(self._ws_connections[room_id]):
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._ws_connections[room_id].discard(ws)

        if room_id in self._sse_queues:
            dead_queues = []
            for queue in list(self._sse_queues[room_id]):
                try:
                    queue.put_nowait(data)
                except asyncio.QueueFull:
                    dead_queues.append(queue)
            for q in dead_queues:
                self._sse_queues[room_id].discard(q)

    # --- Cross-process broadcast via Postgres NOTIFY ---

    async def broadcast(self, room_id: UUID, message: dict):
        """Broadcast to all processes via Postgres NOTIFY.

        Every process (including this one) receives the NOTIFY on its dedicated
        listener connection and calls broadcast_local().  This makes broadcast()
        eventually consistent across all workers; latency is a single Postgres
        round-trip (~1–5 ms on local/cloud networks).
        """
        from ..database import get_pool
        payload = json.dumps({"room_id": str(room_id), "message": message}, default=str)
        pool = get_pool()
        # NOTIFY payload is limited to 8000 bytes by Postgres
        if len(payload) > 7900:
            # Fall back to local-only delivery for oversized messages
            await self.broadcast_local(room_id, message)
            return
        await pool.execute("SELECT pg_notify('octopus_events', $1)", payload)

    # --- Typing indicators (local-only, low priority) ---

    async def broadcast_typing(self, room_id: UUID, user_name: str, sender_ws: WebSocket | None = None):
        """Broadcast typing indicator to in-process connections only (best-effort)."""
        data = json.dumps({"type": "typing", "user": user_name})
        if room_id in self._ws_connections:
            dead = []
            for ws in list(self._ws_connections[room_id]):
                if ws is sender_ws:
                    continue
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._ws_connections[room_id].discard(ws)

    # --- Health ping ---

    async def ping_all(self):
        """Send a ping to every WebSocket; remove any that fail."""
        import logging
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
            logging.getLogger("octopus").info(
                "ping_all: removed %d dead connection(s)", total_removed
            )


manager = ConnectionManager()
