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
async def test_update_page_notifies_and_invalidates_collab(scope, _db_pool):
    scope_id, user_id = scope
    page = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Live", created_by=user_id, content="v1"
    )
    # Simulate a persisted collab doc (as if the page had been opened in the editor).
    await _db_pool.execute(
        "INSERT INTO page_collab_documents (page_id, owner_user_id, yjs_state) VALUES ($1, $2, $3)",
        page["id"],
        scope_id,
        b"\x00",
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
    # Stale collab state was dropped so a reopened editor reloads fresh content.
    remaining = await _db_pool.fetchval(
        "SELECT count(*) FROM page_collab_documents WHERE page_id = $1", page["id"]
    )
    assert remaining == 0


@pytest.mark.asyncio
async def test_collab_projection_save_does_not_notify(scope, _db_pool):
    """The editor's own Yjs->DB projection (notify=False) must not broadcast or
    wipe collab state — that would fight the live editor."""
    scope_id, user_id = scope
    page = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Editing", created_by=user_id, content="a"
    )
    await _db_pool.execute(
        "INSERT INTO page_collab_documents (page_id, owner_user_id, yjs_state) VALUES ($1, $2, $3)",
        page["id"],
        scope_id,
        b"\x00",
    )
    queue = page_events.subscribe(scope_id)
    try:
        await files_tree_service.update_page(page["id"], scope_id, user_id, content="b", notify=False)
        await asyncio.sleep(0.05)
        empty = queue.empty()
    finally:
        page_events.unsubscribe(scope_id, queue)

    assert empty  # no broadcast
    kept = await _db_pool.fetchval(
        "SELECT count(*) FROM page_collab_documents WHERE page_id = $1", page["id"]
    )
    assert kept == 1  # collab state preserved
