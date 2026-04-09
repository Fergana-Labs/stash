"""Integration tests for the ConnectionManager and WebSocket plumbing.

The ConnectionManager is the real-time delivery backbone.  We test it directly
because Starlette's sync TestClient creates its own event loop, which conflicts
with the pytest-asyncio pool fixtures.
"""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.services.connection_manager import ConnectionManager


@pytest.mark.asyncio
async def test_broadcast_local_delivers_to_ws():
    mgr = ConnectionManager()
    room_id = uuid4()

    ws = AsyncMock()
    mgr.ws_connect(room_id, ws)

    await mgr.broadcast_local(room_id, {"type": "message", "content": "hello"})
    ws.send_text.assert_awaited_once()
    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload["content"] == "hello"


@pytest.mark.asyncio
async def test_broadcast_local_delivers_to_sse():
    mgr = ConnectionManager()
    room_id = uuid4()

    queue = mgr.sse_subscribe(room_id)
    await mgr.broadcast_local(room_id, {"type": "message", "content": "sse-hello"})

    data = queue.get_nowait()
    payload = json.loads(data)
    assert payload["content"] == "sse-hello"


@pytest.mark.asyncio
async def test_broadcast_local_delivers_to_multiple_ws():
    mgr = ConnectionManager()
    room_id = uuid4()

    ws1 = AsyncMock()
    ws2 = AsyncMock()
    mgr.ws_connect(room_id, ws1)
    mgr.ws_connect(room_id, ws2)

    await mgr.broadcast_local(room_id, {"type": "message", "content": "all"})
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_local_removes_dead_ws():
    mgr = ConnectionManager()
    room_id = uuid4()

    alive = AsyncMock()
    dead = AsyncMock()
    dead.send_text.side_effect = RuntimeError("connection closed")
    mgr.ws_connect(room_id, alive)
    mgr.ws_connect(room_id, dead)

    await mgr.broadcast_local(room_id, {"type": "ping"})

    alive.send_text.assert_awaited_once()
    assert dead not in mgr._ws_connections.get(room_id, set())
    assert alive in mgr._ws_connections[room_id]


@pytest.mark.asyncio
async def test_ws_connect_disconnect():
    mgr = ConnectionManager()
    room_id = uuid4()
    ws = AsyncMock()

    mgr.ws_connect(room_id, ws)
    assert ws in mgr._ws_connections[room_id]

    mgr.ws_disconnect(room_id, ws)
    assert room_id not in mgr._ws_connections


@pytest.mark.asyncio
async def test_sse_subscribe_unsubscribe():
    mgr = ConnectionManager()
    room_id = uuid4()

    queue = mgr.sse_subscribe(room_id)
    assert room_id in mgr._sse_queues

    mgr.sse_unsubscribe(room_id, queue)
    assert room_id not in mgr._sse_queues


@pytest.mark.asyncio
async def test_typing_skips_sender():
    mgr = ConnectionManager()
    room_id = uuid4()

    sender = AsyncMock()
    receiver = AsyncMock()
    mgr.ws_connect(room_id, sender)
    mgr.ws_connect(room_id, receiver)

    await mgr.broadcast_typing(room_id, "alice", sender_ws=sender)

    sender.send_text.assert_not_awaited()
    receiver.send_text.assert_awaited_once()
    payload = json.loads(receiver.send_text.call_args[0][0])
    assert payload["type"] == "typing"
    assert payload["user"] == "alice"


@pytest.mark.asyncio
async def test_ping_all_removes_dead():
    mgr = ConnectionManager()
    room_id = uuid4()

    alive = AsyncMock()
    dead = AsyncMock()
    dead.send_text.side_effect = ConnectionError
    mgr.ws_connect(room_id, alive)
    mgr.ws_connect(room_id, dead)

    await mgr.ping_all()

    assert alive in mgr._ws_connections[room_id]
    assert dead not in mgr._ws_connections.get(room_id, set())


@pytest.mark.asyncio
async def test_broadcast_uses_pg_notify(pool):
    """Verify broadcast() sends a Postgres NOTIFY (not just local delivery)."""
    mgr = ConnectionManager()
    room_id = uuid4()

    received = []

    conn = await pool.acquire()
    try:
        def on_notify(conn, pid, channel, payload):
            received.append(json.loads(payload))

        await conn.add_listener("octopus_events", on_notify)

        await mgr.broadcast(room_id, {"type": "message", "content": "cross-process"})

        await asyncio.sleep(0.2)

        assert len(received) == 1
        assert received[0]["room_id"] == str(room_id)
        assert received[0]["message"]["content"] == "cross-process"

        await conn.remove_listener("octopus_events", on_notify)
    finally:
        await pool.release(conn)


@pytest.mark.asyncio
async def test_broadcast_falls_back_for_oversized_payload(pool):
    """Messages > 7900 bytes should fall back to broadcast_local only."""
    mgr = ConnectionManager()
    room_id = uuid4()

    ws = AsyncMock()
    mgr.ws_connect(room_id, ws)

    big_content = "x" * 8000
    await mgr.broadcast(room_id, {"type": "message", "content": big_content})

    ws.send_text.assert_awaited_once()
    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload["content"] == big_content
