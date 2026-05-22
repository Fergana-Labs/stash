"""Tests for the public landing-page demo router.

The demo router exposes six anonymous endpoints. These tests exercise
all of them end-to-end through the FastAPI ASGI client, plus the
visibility flags on the resulting Stash and the auto-attached KB
folder.

Conftest disables the boot-time seed (so other tests get clean
workspaces). These tests opt in by calling `seed_demo_workspace`
themselves before each scenario.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from backend.services import demo_service


@pytest_asyncio.fixture(autouse=True)
async def _seed_demo(_db_pool):
    """Every demo test needs the Demo workspace + KB folder pre-seeded.

    Conftest cleanup runs *after* the test so the seed survives the test
    body; the next test gets a fresh seed.
    """
    await demo_service.seed_demo_workspace()
    yield


@pytest.mark.asyncio
async def test_start_returns_instructions(client: AsyncClient):
    resp = await client.get("/api/v1/demo/start")
    assert resp.status_code == 200, resp.text
    body = resp.text
    # The agent must be told the three publish endpoints by name.
    assert "/api/v1/demo/pages" in body
    assert "/api/v1/demo/sessions" in body
    assert "/api/v1/demo/stashes" in body


@pytest.mark.asyncio
async def test_skill_returns_canonical_slides_skill(client: AsyncClient):
    resp = await client.get("/api/v1/demo/skill")
    assert resp.status_code == 200
    body = resp.text
    # Guard against a regression that strips the canvas spec — the whole
    # point of serving this is that agents follow it.
    assert "1920" in body and "1080" in body


@pytest.mark.asyncio
async def test_about_returns_stash_pitch(client: AsyncClient):
    resp = await client.get("/api/v1/demo/about")
    assert resp.status_code == 200
    assert "Stash" in resp.text


@pytest.mark.asyncio
async def test_full_publish_flow(client: AsyncClient):
    """End-to-end: page + session + stash → returns a public app_url."""
    page_resp = await client.post(
        "/api/v1/demo/pages",
        json={
            "title": "Stash deck for Test Visitor",
            "html": "<html><body><section class='slide'><h1>Hi</h1></section></body></html>",
            "html_layout": "fixed-aspect",
        },
    )
    assert page_resp.status_code == 201, page_resp.text
    page_id = page_resp.json()["page_id"]

    session_resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "Stash demo Q&A with Test Visitor",
            "transcript": "**Q:** What's your name?\n**A:** Test Visitor",
            "agent_name": "test-agent",
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["session_id"]

    stash_resp = await client.post(
        "/api/v1/demo/stashes",
        json={
            "title": "Stash for Test Visitor",
            "description": "Demo from the landing page",
            "items": [
                {"object_type": "page", "object_id": page_id},
                {"object_type": "session", "object_id": session_id},
            ],
        },
    )
    assert stash_resp.status_code == 201, stash_resp.text
    body = stash_resp.json()
    assert body["app_url"].endswith(f"/stashes/{body['slug']}")
    assert body["slug"]


@pytest.mark.asyncio
async def test_stash_is_public_unlisted_and_includes_kb_folder(
    client: AsyncClient, pool
):
    """Demo Stashes must be public-link-shareable but not discoverable, and
    must auto-include the canonical Stash knowledge base folder."""
    page = (
        await client.post(
            "/api/v1/demo/pages",
            json={"title": "T", "html": "<html><body><section class='slide'>x</section></body></html>"},
        )
    ).json()
    stash = (
        await client.post(
            "/api/v1/demo/stashes",
            json={
                "title": "Visibility check",
                "items": [{"object_type": "page", "object_id": page["page_id"]}],
            },
        )
    ).json()

    row = await pool.fetchrow(
        "SELECT workspace_permission, public_permission, discoverable "
        "FROM stashes WHERE id = $1",
        stash["stash_id"],
    )
    assert row["workspace_permission"] == "none"
    assert row["public_permission"] == "read"
    assert row["discoverable"] is False

    # The KB folder must be attached as a stash item even though we only
    # passed the page in.
    folder_id = await demo_service.get_kb_folder_id()
    items = await pool.fetch(
        "SELECT object_type, object_id FROM stash_items WHERE stash_id = $1",
        stash["stash_id"],
    )
    pairs = {(r["object_type"], str(r["object_id"])) for r in items}
    assert ("folder", str(folder_id)) in pairs


@pytest.mark.asyncio
async def test_kb_folder_is_reused_across_demos(client: AsyncClient, pool):
    """Two demos in a row must reference the same KB folder, not create
    duplicates. Otherwise we'd hit DuplicateFolderName quickly."""
    folder_id_before = await demo_service.get_kb_folder_id()
    for _ in range(2):
        page = (
            await client.post(
                "/api/v1/demo/pages",
                json={"title": "T", "html": "<html><body><section class='slide'>x</section></body></html>"},
            )
        ).json()
        resp = await client.post(
            "/api/v1/demo/stashes",
            json={
                "title": "Reuse check",
                "items": [{"object_type": "page", "object_id": page["page_id"]}],
            },
        )
        assert resp.status_code == 201, resp.text
    folder_id_after = await demo_service.get_kb_folder_id()
    assert folder_id_before == folder_id_after
    # And nobody created a sibling folder with the same name.
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM folders WHERE name = $1",
        "Stash knowledge base",
    )
    assert count == 1


@pytest.mark.asyncio
async def test_rejects_items_outside_demo_workspace(client: AsyncClient, pool):
    """Forbid bundling a page from some other workspace into a demo Stash."""
    # Create a non-demo workspace + page directly via SQL.
    from uuid import uuid4

    user_id = await pool.fetchval(
        "INSERT INTO users (name, display_name) VALUES ($1, $2) RETURNING id",
        f"outsider-{uuid4().hex[:8]}",
        "Outsider",
    )
    ws_id = await pool.fetchval(
        "INSERT INTO workspaces (name, description, creator_id, invite_code) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "Outsider WS",
        "",
        user_id,
        uuid4().hex[:8],
    )
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) "
        "VALUES ($1, $2, 'owner')",
        ws_id,
        user_id,
    )
    outside_page_id = await pool.fetchval(
        "INSERT INTO pages (workspace_id, name, content_markdown, content_html, "
        "content_type, html_layout, content_hash, metadata, created_by, updated_by) "
        "VALUES ($1, $2, '', '', 'markdown', 'responsive', 'hash', '{}'::jsonb, $3, $3) "
        "RETURNING id",
        ws_id,
        "Outside page",
        user_id,
    )

    resp = await client.post(
        "/api/v1/demo/stashes",
        json={
            "title": "Cross-workspace attempt",
            "items": [{"object_type": "page", "object_id": str(outside_page_id)}],
        },
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_janitor_purges_orphans_keeps_referenced(client: AsyncClient, pool):
    """Pages/sessions referenced by a Stash survive; lone orphans do not.
    The canonical KB folder pages are also kept regardless of age."""
    from backend.tasks.demo_janitor import _purge_demo_orphans

    referenced_page = (
        await client.post(
            "/api/v1/demo/pages",
            json={"title": "Kept", "html": "<html><body><section class='slide'>x</section></body></html>"},
        )
    ).json()
    await client.post(
        "/api/v1/demo/stashes",
        json={
            "title": "Referenced",
            "items": [{"object_type": "page", "object_id": referenced_page["page_id"]}],
        },
    )

    orphan_page = (
        await client.post(
            "/api/v1/demo/pages",
            json={"title": "Orphan", "html": "<html><body><section class='slide'>x</section></body></html>"},
        )
    ).json()
    orphan_session = (
        await client.post(
            "/api/v1/demo/sessions",
            json={"title": "Orphan Q&A", "transcript": "dropped on the floor"},
        )
    ).json()

    # Backdate the orphans so they cross the retention threshold.
    await pool.execute(
        "UPDATE pages SET created_at = now() - interval '48 hours' WHERE id = $1",
        orphan_page["page_id"],
    )
    await pool.execute(
        "UPDATE sessions SET started_at = now() - interval '48 hours' WHERE id = $1",
        orphan_session["session_id"],
    )

    result = await _purge_demo_orphans()
    assert result["pages"] >= 1
    assert result["sessions"] >= 1

    referenced_alive = await pool.fetchval(
        "SELECT 1 FROM pages WHERE id = $1 AND deleted_at IS NULL",
        referenced_page["page_id"],
    )
    assert referenced_alive == 1

    orphan_alive = await pool.fetchval(
        "SELECT 1 FROM pages WHERE id = $1", orphan_page["page_id"]
    )
    assert orphan_alive is None


@pytest.mark.asyncio
async def test_session_event_is_visible(client: AsyncClient, pool):
    """Session create should also push an event so the Q&A actually shows
    up when the Stash renders the session inline."""
    resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "Event sanity check",
            "transcript": "the-transcript-marker",
            "agent_name": "test-agent",
        },
    )
    session_row_id = resp.json()["session_id"]
    content = await pool.fetchval(
        "SELECT content FROM history_events WHERE session_id = ("
        "  SELECT session_id FROM sessions WHERE id = $1"
        ") LIMIT 1",
        session_row_id,
    )
    assert content is not None
    assert "the-transcript-marker" in content
