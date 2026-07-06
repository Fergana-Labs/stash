"""The daily Memory curator: provisioning, change feed, cost gate, prompt."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import agent_service, curation_service, prompts

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("cur"), "password": "securepassword1"},
    )
    return r.json()["api_key"], UUID(r.json()["id"])


def _auth(k: str) -> dict:
    return {"Authorization": f"Bearer {k}"}


@pytest.mark.asyncio
async def test_curator_provisioned_reserved_and_due(client: AsyncClient, _db_pool):
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    assert curator["is_curator"] and curator["run_mode"] == "scheduled"
    assert curator["schedule_cron"] and curator["schedule_prompt"] is None
    # Seeded watermark (backfill), so the cron can become due — not NULL.
    assert curator["last_run_at"] is not None
    # Idempotent — same row on second call.
    again = await agent_service.get_or_create_curator(uid)
    assert again["id"] == curator["id"]


@pytest.mark.asyncio
async def test_curator_cannot_be_deleted(client: AsyncClient):
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    r = await client.delete(f"/api/v1/me/agents/{curator['id']}", headers=_auth(key))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_curator_provisioned_on_activity_via_chat(client: AsyncClient, sprite_exec):
    # A web chat turn is activity → the curator should be auto-provisioned.
    key, uid = await _register(client)
    await client.post("/api/v1/me/agent-chat", json={"message": "hi"}, headers=_auth(key))
    agents = (await client.get("/api/v1/me/agents", headers=_auth(key))).json()["agents"]
    assert any(a["is_curator"] for a in agents)


@pytest.mark.asyncio
async def test_has_changes_and_feed_exclude_memory(client: AsyncClient, _db_pool):
    key, uid = await _register(client)
    old = datetime(2020, 1, 1, tzinfo=UTC)

    # A page in Files counts as a change.
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Notes", "content": "a real note"},
        headers=_auth(key),
    )
    assert await curation_service.has_changes_since(uid, uid, old) is True

    feed = await curation_service.changes_since(uid, uid, old)
    assert any(p["name"] == "Notes" for p in feed["pages"])

    # A page written INTO the Memory folder must NOT appear (no self-curation).
    mem = (await client.get("/api/v1/me/memory-folder", headers=_auth(key))).json()
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Wiki Page", "content": "curated", "folder_id": mem["id"]},
        headers=_auth(key),
    )
    feed2 = await curation_service.changes_since(uid, uid, old)
    assert all(p["name"] != "Wiki Page" for p in feed2["pages"])


@pytest.mark.asyncio
async def test_has_changes_false_after_watermark(client: AsyncClient, _db_pool):
    key, uid = await _register(client)
    await client.post(
        "/api/v1/me/pages/new", json={"name": "P", "content": "x"}, headers=_auth(key)
    )
    future = datetime.now(UTC) + timedelta(hours=1)
    # Nothing changed after a future watermark → no changes → curator skipped.
    assert await curation_service.has_changes_since(uid, uid, future) is False


@pytest.mark.asyncio
async def test_changes_endpoint(client: AsyncClient):
    key, uid = await _register(client)
    r = await client.get("/api/v1/me/changes?since=2020-01-01T00:00:00", headers=_auth(key))
    assert r.status_code == 200
    body = r.json()
    assert "counts" in body and "history" in body and "pages" in body


def test_curator_prompt_embeds_folder_and_window():
    boot = prompts.render_curator_prompt("folder-123", None)
    assert "folder-123" in boot and "bootstrap" in boot.lower()
    maint = prompts.render_curator_prompt("folder-123", "2026-07-06T09:00:00")
    assert "2026-07-06T09:00:00" in maint and "stash changes --since" in maint


@pytest.mark.asyncio
async def test_idle_curator_skipped_by_beat(client: AsyncClient, sprite_exec, _db_pool):
    """A curator whose watermark is in the future (no changes) is skipped, and
    its watermark is preserved (not advanced)."""
    from backend.tasks.agent_schedules import _run_due

    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    # Make it due but with nothing changed since a future watermark.
    future = datetime.now(UTC) + timedelta(hours=1)
    await _db_pool.execute(
        "UPDATE agents SET schedule_cron = '* * * * *', last_run_at = $2 WHERE id = $1",
        UUID(curator["id"]), future,
    )
    before = await _db_pool.fetchval(
        "SELECT last_run_at FROM agents WHERE id = $1", UUID(curator["id"])
    )
    await _run_due()
    after = await _db_pool.fetchval(
        "SELECT last_run_at FROM agents WHERE id = $1", UUID(curator["id"])
    )
    assert before == after  # skipped, watermark preserved
