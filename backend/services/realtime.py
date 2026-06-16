"""Cross-instance realtime change-feed on Postgres LISTEN/NOTIFY.

Dashboards subscribe (over SSE) to a table's row changes and refetch when they
fire. The bus routes through Postgres so it works across horizontally-scaled web
instances — unlike the in-process `page_events`, which only reaches subscribers
on the same process.

Each `emit` dispatches to local subscribers immediately (so same-instance
delivery works without the listener — e.g. in tests) and fires a NOTIFY for
other instances. The listener skips events that originated in this process so
they aren't delivered twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from ..database import get_pool

logger = logging.getLogger(__name__)

CHANNEL = "stash_realtime"

# This process's id — lets the NOTIFY listener drop events it already dispatched
# locally on emit (avoids double-delivery on the originating instance).
_ORIGIN = uuid.uuid4().hex

# routing key (e.g. "table:<uuid>") -> set of subscriber queues. Bounded queues
# drop events for a stalled client rather than grow without bound; the client
# refetches on the next event it does receive.
_subscribers: dict[str, set[asyncio.Queue]] = {}

_listen_conn = None


def table_key(table_id) -> str:
    return f"table:{table_id}"


def subscribe(key: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.setdefault(key, set()).add(queue)
    return queue


def unsubscribe(key: str, queue: asyncio.Queue) -> None:
    subs = _subscribers.get(key)
    if not subs:
        return
    subs.discard(queue)
    if not subs:
        _subscribers.pop(key, None)


def _dispatch_local(key: str, event: dict) -> None:
    for queue in list(_subscribers.get(key, ())):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("realtime queue full for %s; dropping event", key)


def emit(key: str, event: dict) -> None:
    """Dispatch to local subscribers now and notify other instances. Non-blocking."""
    _dispatch_local(key, event)
    try:
        asyncio.get_running_loop().create_task(_notify(key, event))
    except RuntimeError:
        # No running loop (e.g. called from sync teardown) — local dispatch already happened.
        pass


async def _notify(key: str, event: dict) -> None:
    payload = json.dumps({"origin": _ORIGIN, "key": key, "event": event})
    try:
        await get_pool().execute("SELECT pg_notify($1, $2)", CHANNEL, payload)
    except Exception:
        # Cross-instance delivery is best-effort; a NOTIFY hiccup must not fail the write.
        logger.exception("realtime NOTIFY failed for %s", key)


def _on_notify(_conn, _pid, _channel, payload: str) -> None:
    msg = json.loads(payload)
    if msg["origin"] == _ORIGIN:
        return  # already dispatched locally on emit
    _dispatch_local(msg["key"], msg["event"])


async def start() -> None:
    """Open the dedicated LISTEN connection. Called from the app lifespan."""
    global _listen_conn
    if _listen_conn is not None:
        return
    _listen_conn = await get_pool().acquire()
    await _listen_conn.add_listener(CHANNEL, _on_notify)


async def stop() -> None:
    global _listen_conn
    if _listen_conn is None:
        return
    await _listen_conn.remove_listener(CHANNEL, _on_notify)
    await get_pool().release(_listen_conn)
    _listen_conn = None
