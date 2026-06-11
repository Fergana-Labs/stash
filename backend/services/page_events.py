"""In-process pub/sub for live page updates.

When the backend writes a page (an agent edit, a REST save, a copy), open
viewers should see it without a manual refresh. Subscribers (SSE connections)
register a queue per workspace; writers publish a small event. This is
process-local — fine because the web app runs as a single uvicorn process; if
that ever scales horizontally, swap publish/listen for Postgres LISTEN/NOTIFY.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# workspace_id -> set of subscriber queues. Bounded queues drop events for a
# stalled client rather than grow without limit; the client refetches on the
# next event it does receive.
_subscribers: dict[UUID, set[asyncio.Queue]] = {}


def subscribe(workspace_id: UUID) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.setdefault(workspace_id, set()).add(queue)
    return queue


def unsubscribe(workspace_id: UUID, queue: asyncio.Queue) -> None:
    subs = _subscribers.get(workspace_id)
    if not subs:
        return
    subs.discard(queue)
    if not subs:
        _subscribers.pop(workspace_id, None)


def publish_page_update(
    workspace_id: UUID,
    page_id: UUID,
    content_hash: str | None,
    agent_name: str | None = None,
) -> None:
    """Notify subscribers that a page's content changed. Safe to call from sync
    or async code — it never blocks (full queues drop the event)."""
    event = {
        "type": "page.updated",
        "page_id": str(page_id),
        "content_hash": content_hash,
        "agent_name": agent_name,
    }
    for queue in list(_subscribers.get(workspace_id, ())):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("page_events queue full for workspace %s; dropping event", workspace_id)
