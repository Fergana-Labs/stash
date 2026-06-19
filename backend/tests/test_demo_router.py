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
    assert "/api/v1/demo/skills" in body


@pytest.mark.asyncio
async def test_skill_returns_canonical_slides_skill(client: AsyncClient):
    resp = await client.get("/api/v1/demo/skill")
    assert resp.status_code == 200
    body = resp.text
    # Guard against a regression that strips the canvas spec — the whole
    # point of serving this is that agents follow it.
    assert "1920" in body and "1080" in body


@pytest.mark.asyncio
async def test_about_returns_skill_pitch(client: AsyncClient):
    resp = await client.get("/api/v1/demo/about")
    assert resp.status_code == 200
    assert "Stash" in resp.text


@pytest.mark.asyncio
async def test_full_publish_flow(client: AsyncClient):
    """End-to-end: page + session + skill → returns a public app_url."""
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
            "agent_name": "test-agent",
            "events": [
                {"event_type": "user_message", "content": "Paste of demo prompt"},
                {"event_type": "assistant_message", "content": "What's your name?"},
                {"event_type": "user_message", "content": "Test Visitor"},
            ],
        },
    )
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["session_id"]

    stash_resp = await client.post(
        "/api/v1/demo/skills",
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
    assert body["app_url"].endswith(f"/skills/{body['slug']}")
    assert body["slug"]


@pytest.mark.asyncio
async def test_skill_is_public_unlisted_and_includes_kb_pages(client: AsyncClient, pool):
    """Demo Skills must be public-link-shareable but not discoverable, and
    must auto-copy the canonical Stash knowledge base pages into the skill
    folder so every demo ships self-contained."""
    page = (
        await client.post(
            "/api/v1/demo/pages",
            json={
                "title": "T",
                "html": "<html><body><section class='slide'>x</section></body></html>",
            },
        )
    ).json()
    stash = (
        await client.post(
            "/api/v1/demo/skills",
            json={
                "title": "Visibility check",
                "items": [{"object_type": "page", "object_id": page["page_id"]}],
            },
        )
    ).json()

    row = await pool.fetchrow(
        "SELECT folder_id, discoverable FROM skills WHERE id = $1",
        stash["skill_id"],
    )
    # Published == publicly readable; unlisted means not in Discover.
    assert row["discoverable"] is False
    detail = await client.get(f"/api/v1/skills/{stash['slug']}")
    assert detail.status_code == 200

    # The KB pages must be copied into the skill folder even though we only
    # passed the page in.
    kb_folder_id = await demo_service.get_kb_folder_id()
    kb_names = {
        r["name"]
        for r in await pool.fetch(
            "SELECT name FROM pages WHERE folder_id = $1 AND deleted_at IS NULL",
            kb_folder_id,
        )
    }
    assert kb_names, "seed should have populated the KB folder"
    skill_page_names = {
        r["name"]
        for r in await pool.fetch(
            "SELECT name FROM pages WHERE folder_id = $1 AND deleted_at IS NULL",
            row["folder_id"],
        )
    }
    assert kb_names <= skill_page_names
    # The visitor's deck page was moved into the skill folder too.
    moved_folder = await pool.fetchval("SELECT folder_id FROM pages WHERE id = $1", page["page_id"])
    assert moved_folder == row["folder_id"]


@pytest.mark.asyncio
async def test_kb_folder_is_reused_across_demos(client: AsyncClient, pool):
    """Two demos in a row must reference the same KB folder, not create
    duplicates. Otherwise we'd hit DuplicateFolderName quickly."""
    folder_id_before = await demo_service.get_kb_folder_id()
    for _ in range(2):
        page = (
            await client.post(
                "/api/v1/demo/pages",
                json={
                    "title": "T",
                    "html": "<html><body><section class='slide'>x</section></body></html>",
                },
            )
        ).json()
        resp = await client.post(
            "/api/v1/demo/skills",
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
        "/api/v1/demo/skills",
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
            json={
                "title": "Kept",
                "html": "<html><body><section class='slide'>x</section></body></html>",
            },
        )
    ).json()
    await client.post(
        "/api/v1/demo/skills",
        json={
            "title": "Referenced",
            "items": [{"object_type": "page", "object_id": referenced_page["page_id"]}],
        },
    )

    orphan_page = (
        await client.post(
            "/api/v1/demo/pages",
            json={
                "title": "Orphan",
                "html": "<html><body><section class='slide'>x</section></body></html>",
            },
        )
    ).json()
    orphan_session = (
        await client.post(
            "/api/v1/demo/sessions",
            json={
                "title": "Orphan Q&A",
                "events": [{"event_type": "user_message", "content": "dropped on the floor"}],
            },
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

    orphan_alive = await pool.fetchval("SELECT 1 FROM pages WHERE id = $1", orphan_page["page_id"])
    assert orphan_alive is None


@pytest.mark.asyncio
async def test_session_stores_full_event_timeline(client: AsyncClient, pool):
    """Each turn must land as its own history_event so the Stash session
    viewer renders the conversation as a chat thread. This is what makes
    the demo show *how* the deck was built, not just a summary."""
    events_in = [
        {"event_type": "user_message", "content": "the-paste-marker"},
        {"event_type": "tool_use", "tool_name": "curl", "content": "GET /api/v1/demo/start"},
        {"event_type": "tool_result", "tool_name": "curl", "content": "instructions ..."},
        {"event_type": "assistant_message", "content": "Q1?"},
        {"event_type": "user_message", "content": "A1"},
    ]
    resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "Timeline check",
            "agent_name": "test-agent",
            "events": events_in,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["event_count"] == len(events_in)

    session_row_id = resp.json()["session_id"]
    rows = await pool.fetch(
        "SELECT event_type, content, tool_name FROM history_events "
        "WHERE session_id = (SELECT session_id FROM sessions WHERE id = $1) "
        "ORDER BY created_at ASC, id ASC",
        session_row_id,
    )
    assert len(rows) == len(events_in)
    assert [r["event_type"] for r in rows] == [e["event_type"] for e in events_in]
    assert rows[0]["content"] == "the-paste-marker"
    # Tool name preserved on tool_use rows
    assert rows[1]["tool_name"] == "curl"


@pytest.mark.asyncio
async def test_session_preserves_event_timestamps(client: AsyncClient, pool):
    """Per-event created_at must round-trip. Without this, all events
    cluster at the moment of POST and the timeline looks fake."""
    resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "Timestamp test",
            "agent_name": "test-agent",
            "events": [
                {
                    "event_type": "user_message",
                    "created_at": "2026-05-25T18:20:00+00:00",
                    "content": "first",
                },
                {
                    "event_type": "assistant_message",
                    "created_at": "2026-05-25T18:22:30+00:00",
                    "content": "second",
                },
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    session_row_id = resp.json()["session_id"]
    rows = await pool.fetch(
        "SELECT content, created_at FROM history_events "
        "WHERE session_id = (SELECT session_id FROM sessions WHERE id = $1) "
        "ORDER BY created_at ASC",
        session_row_id,
    )
    assert len(rows) == 2
    delta_seconds = (rows[1]["created_at"] - rows[0]["created_at"]).total_seconds()
    assert delta_seconds == pytest.approx(150.0, abs=1.0)


@pytest.mark.asyncio
async def test_session_persists_cwd(client: AsyncClient, pool):
    """The agent's cwd is part of what makes a real captured session
    look real. Required on the session row."""
    resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "cwd test",
            "agent_name": "test-agent",
            "cwd": "/Users/sam/code/myrepo",
            "events": [{"event_type": "user_message", "content": "x"}],
        },
    )
    assert resp.status_code == 201, resp.text
    cwd = await pool.fetchval("SELECT cwd FROM sessions WHERE id = $1", resp.json()["session_id"])
    assert cwd == "/Users/sam/code/myrepo"


@pytest.mark.asyncio
async def test_session_end_sets_finished_at(client: AsyncClient, pool):
    """A closing session_end event with a timestamp marks the session
    as finished, same as a real harness's end-of-session hook."""
    end_ts = "2026-05-25T18:23:15+00:00"
    resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "session_end test",
            "agent_name": "test-agent",
            "events": [
                {
                    "event_type": "user_message",
                    "content": "kick off",
                    "created_at": "2026-05-25T18:20:00+00:00",
                },
                {"event_type": "session_end", "content": "done", "created_at": end_ts},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    finished_at = await pool.fetchval(
        "SELECT finished_at FROM sessions WHERE id = $1", resp.json()["session_id"]
    )
    assert finished_at is not None
    assert finished_at.isoformat() == end_ts.replace("+00:00", "+00:00")


@pytest.mark.asyncio
async def test_session_end_without_timestamp_leaves_finished_at_null(client: AsyncClient, pool):
    """If the agent forgets to stamp the closing event, we don't guess.
    finished_at stays null, which is the same as a session the harness
    crashed before sending an end hook."""
    resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "no end ts",
            "agent_name": "test-agent",
            "events": [
                {"event_type": "user_message", "content": "kick off"},
                {"event_type": "session_end", "content": "done"},
            ],
        },
    )
    assert resp.status_code == 201
    finished_at = await pool.fetchval(
        "SELECT finished_at FROM sessions WHERE id = $1", resp.json()["session_id"]
    )
    assert finished_at is None


@pytest.mark.asyncio
async def test_session_rejects_unknown_event_type(client: AsyncClient):
    """Constrained event_type means agents can't sneak in arbitrary types
    that the renderer doesn't handle."""
    resp = await client.post(
        "/api/v1/demo/sessions",
        json={
            "title": "Bad type",
            "agent_name": "test-agent",
            "events": [{"event_type": "not_a_real_type", "content": "x"}],
        },
    )
    assert resp.status_code == 422
