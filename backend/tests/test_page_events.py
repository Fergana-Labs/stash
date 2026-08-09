"""Live page updates: the pub/sub fan-out and update_page's notify behavior
(publish an event + invalidate stale collab state on external writes)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import files_tree_service, page_events


@pytest_asyncio.fixture
async def scope(_db_pool):
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    # The scope IS the user; content is owned by owner_user_id = user_id.
    return user_id, user_id


def test_pubsub_delivers_then_stops_after_unsubscribe():
    scope_id = uuid4()
    page = uuid4()
    queue = page_events.subscribe(scope_id)
    page_events.publish_page_update(scope_id, page, "hash1", "Agent")
    event = queue.get_nowait()
    assert event == {
        "type": "page.updated",
        "page_id": str(page),
        "content_hash": "hash1",
        "agent_name": "Agent",
    }
    page_events.unsubscribe(scope_id, queue)
    page_events.publish_page_update(scope_id, page, "hash2", None)  # no subscribers; no error
    assert queue.empty()


@pytest.mark.asyncio
async def test_update_page_notifies_open_viewers(scope, _db_pool):
    """A content write broadcasts so open viewers refetch. (The collab-state
    invalidation this test also covered is gone with the collab server: there
    is no second copy of the document to go stale.)"""
    scope_id, user_id = scope
    page = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Live", created_by=user_id, content="v1"
    )
    queue = page_events.subscribe(scope_id)
    try:
        await files_tree_service.update_page(
            page["id"], scope_id, user_id, content="v2", edit_agent_name="Stash Agent"
        )
        event = await asyncio.wait_for(queue.get(), timeout=1)
    finally:
        page_events.unsubscribe(scope_id, queue)

    assert event["page_id"] == str(page["id"])
    assert event["agent_name"] == "Stash Agent"
