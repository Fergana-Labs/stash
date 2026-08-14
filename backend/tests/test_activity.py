import json
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(prefix), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


async def _scope(client: AsyncClient, api_key: str) -> dict:
    # A user IS their own scope, so the scope id/name come straight off the
    # authenticated profile.
    resp = await client.get("/api/v1/users/me", headers=_auth(api_key))
    assert resp.status_code == 200
    return resp.json()


async def _event(
    client: AsyncClient,
    api_key: str,
    owner_user_id: str,
    session_id: str,
    agent_name: str = "tester",
    created_at: str = "2026-01-02T00:00:00Z",
) -> None:
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": agent_name,
            "event_type": "assistant_message",
            "content": session_id,
            "session_id": session_id,
            "created_at": created_at,
        },
        headers=_auth(api_key),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_activity_timeline_pivots_on_human_and_agent_sessions(client: AsyncClient):
    register_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("activity_timeline"),
            "display_name": "Timeline Human",
            "password": "securepassword1",
        },
    )
    assert register_resp.status_code == 201
    api_key = register_resp.json()["api_key"]
    scope = await _scope(client, api_key)

    for content in ("first event", "second event"):
        event_resp = await client.post(
            "/api/v1/me/sessions/events",
            json={
                "agent_name": "codex",
                "event_type": "assistant_message",
                "content": content,
                "session_id": "same-session",
            },
            headers=_auth(api_key),
        )
        assert event_resp.status_code == 201

    page_resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Not a contributor", "content": "page content"},
        headers=_auth(api_key),
    )
    assert page_resp.status_code == 201

    resp = await client.get(
        "/api/v1/me/activity-timeline",
        params={"days": 365, "owner_user_id": scope["id"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    timeline = resp.json()
    assert timeline["contributors"] == ["Timeline Human (codex)"]
    assert "Pages" not in timeline["contributors"]

    totals = [
        contributor["total"]
        for bucket in timeline["buckets"]
        for contributor in bucket["contributors"].values()
    ]
    assert totals == [1]


@pytest.mark.asyncio
async def test_user_wide_knowledge_density_ignores_stale_cache_without_current_access(
    client: AsyncClient,
    pool,
):
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("stale_density"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    user_id = UUID(body["id"])

    await pool.execute(
        "INSERT INTO knowledge_density_cache "
        "(user_id, owner_user_id, clusters, source_signature, computed_at) "
        "VALUES ($1, NULL, $2::jsonb, 0, now())",
        user_id,
        json.dumps(
            [
                {
                    "label": "Webflow acquisition plan",
                    "count": 1,
                    "newest_at": "2026-06-01T00:00:00Z",
                }
            ]
        ),
    )

    density = await client.get(
        "/api/v1/me/knowledge-density",
        headers=_auth(body["api_key"]),
    )

    assert density.status_code == 200
    assert density.json()["clusters"] == []


@pytest.mark.asyncio
async def test_user_wide_embedding_projection_ignores_stale_cache_without_current_access(
    client: AsyncClient,
    pool,
):
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("stale_projection"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    user_id = UUID(body["id"])

    await pool.execute(
        "INSERT INTO embedding_projections "
        "(user_id, source_type, owner_user_id, points, embedding_count, computed_at) "
        "VALUES ($1, '_all', NULL, $2::jsonb, 0, now())",
        user_id,
        json.dumps(
            [
                {
                    "id": "stale-webflow-point",
                    "x": 0,
                    "y": 0,
                    "z": 0,
                    "source": "history_events",
                    "label": "Webflow confidential transcript",
                    "created_at": "2026-06-01T00:00:00Z",
                }
            ]
        ),
    )

    projection = await client.get(
        "/api/v1/me/embedding-projection",
        headers=_auth(body["api_key"]),
    )

    assert projection.status_code == 200
    assert projection.json() == {
        "points": [],
        "stats": {"total_embeddings": 0, "projected": 0},
        "cached": False,
    }


@pytest.mark.asyncio
async def test_scoped_embedding_projection_serves_cache(
    client: AsyncClient,
    pool,
):
    """The memory page's embeddings map must come from the cache, not an
    inline UMAP fit — recomputing per load is the minute-long-render bug.
    Cache rows are scope-keyed: (user, user) is the personal scope every
    home load requests."""
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("cached_projection"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    user_id = UUID(body["id"])

    point = {
        "id": "cached-point",
        "x": 0.1,
        "y": 0.2,
        "z": 0.3,
        "source": "pages",
        "label": "Roadmap",
        "created_at": "2026-07-01T00:00:00Z",
    }
    await pool.execute(
        "INSERT INTO embedding_projections "
        "(user_id, source_type, owner_user_id, points, embedding_count, scope_signature, computed_at) "
        "VALUES ($1, '_all', $1, $2, 0, NULL, now())",
        user_id,
        [point],
    )

    projection = await client.get(
        "/api/v1/me/embedding-projection",
        headers=_auth(body["api_key"]),
    )

    assert projection.status_code == 200
    assert projection.json() == {
        "points": [point],
        "stats": {"total_embeddings": 0, "projected": 1},
        "cached": True,
    }


@pytest.mark.asyncio
async def test_activity_timeline_includes_blank_day_buckets(client: AsyncClient):
    api_key = await _register(client, "activity_blank_days")
    scope = await _scope(client, api_key)
    event_day = datetime.now(UTC).date() - timedelta(days=1)
    event_at = datetime.combine(event_day, time(hour=12), tzinfo=UTC)

    await _event(
        client,
        api_key,
        scope["id"],
        "middle-day-session",
        created_at=event_at.isoformat(),
    )

    resp = await client.get(
        "/api/v1/me/activity-timeline",
        params={"days": 3, "bucket": "day", "owner_user_id": scope["id"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    buckets = resp.json()["buckets"]
    assert len(buckets) == 3

    active_buckets = [bucket for bucket in buckets if bucket["contributors"]]
    assert len(active_buckets) == 1
    assert datetime.fromisoformat(active_buckets[0]["date"]).date() == event_day

    blank_buckets = [bucket for bucket in buckets if not bucket["contributors"]]
    assert len(blank_buckets) == 2


@pytest.mark.asyncio
async def test_activity_timeline_uses_client_name_for_agent_label(client: AsyncClient):
    register_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("activity_client_label"),
            "display_name": "Client Human",
            "password": "securepassword1",
        },
    )
    assert register_resp.status_code == 201
    api_key = register_resp.json()["api_key"]
    scope = await _scope(client, api_key)

    event_resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "user",
            "event_type": "assistant_message",
            "content": "done",
            "session_id": "client-label-session",
            "metadata": {"client": "codex_cli"},
        },
        headers=_auth(api_key),
    )
    assert event_resp.status_code == 201

    claude_event_resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "user",
            "event_type": "assistant_message",
            "content": "done",
            "session_id": "claude-client-label-session",
            "metadata": {"client": "claude_code"},
        },
        headers=_auth(api_key),
    )
    assert claude_event_resp.status_code == 201

    resp = await client.get(
        "/api/v1/me/activity-timeline",
        params={"days": 365, "owner_user_id": scope["id"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    timeline = resp.json()
    assert timeline["contributors"] == [
        "Client Human (claude code)",
        "Client Human (codex)",
    ]


@pytest.mark.asyncio
async def test_activity_timeline_normalizes_claude_code_agent_names(client: AsyncClient):
    register_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("activity_claude_subagents"),
            "display_name": "Claude Human",
            "password": "securepassword1",
        },
    )
    assert register_resp.status_code == 201
    api_key = register_resp.json()["api_key"]
    scope = await _scope(client, api_key)

    await _event(client, api_key, scope["id"], "claude-parent", "claude")
    await _event(client, api_key, scope["id"], "claude-child", "claude-subagent")
    await _event(client, api_key, scope["id"], "claude-prefixed", "sam-claude-code")

    resp = await client.get(
        "/api/v1/me/activity-timeline",
        params={"days": 365, "owner_user_id": scope["id"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    timeline = resp.json()
    assert timeline["contributors"] == ["Claude Human (claude code)"]

    totals = [
        contributor["total"]
        for bucket in timeline["buckets"]
        for contributor in bucket["contributors"].values()
    ]
    assert totals == [3]


@pytest.mark.asyncio
async def test_file_activity_is_scoped_and_excludes_memory(client: AsyncClient):
    owner_key = await _register(client, "activity_owner")
    other_key = await _register(client, "activity_other")

    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Visible page", "content": "hello"},
        headers=_auth(owner_key),
    )
    assert page.status_code == 201
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Hidden page", "content": "other scope"},
        headers=_auth(other_key),
    )
    # A page in the Memory subtree is curation output, not file activity.
    mem = (await client.get("/api/v1/me/memory-folder", headers=_auth(owner_key))).json()
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Wiki page", "content": "curated", "folder_id": mem["id"]},
        headers=_auth(owner_key),
    )

    resp = await client.get(
        "/api/v1/me/file-activity", params={"limit": 200}, headers=_auth(owner_key)
    )
    assert resp.status_code == 200
    labels = [e["target_label"] for e in resp.json()["events"]]
    assert "Visible page" in labels
    assert "Hidden page" not in labels
    assert "Wiki page" not in labels


async def _file_row(pool, owner_user_id: UUID, name: str, folder_id: UUID | None) -> None:
    await pool.execute(
        "INSERT INTO files (owner_user_id, name, content_type, size_bytes, storage_key, "
        "uploaded_by, folder_id) VALUES ($1, $2, 'image/png', 9, $2, $1, $3)",
        owner_user_id,
        name,
        folder_id,
    )


@pytest.mark.asyncio
async def test_file_activity_excludes_files_inside_the_memory_subtree(client: AsyncClient, pool):
    """The Memory exclusion is about what the curator churns through, and the
    curator writes files as well as pages — a filter that only covers pages
    leaks half of that churn into Home. Nested folders count too: Memory's
    descendants are Memory."""
    api_key = await _register(client, "activity_mem_files")
    scope = UUID((await _scope(client, api_key))["id"])
    memory_id = UUID(
        (await client.get("/api/v1/me/memory-folder", headers=_auth(api_key))).json()["id"]
    )
    nested_id = await pool.fetchval(
        "INSERT INTO folders (owner_user_id, parent_folder_id, name, created_by) "
        "VALUES ($1, $2, 'Wiki', $1) RETURNING id",
        scope,
        memory_id,
    )

    await _file_row(pool, scope, "Loose file", None)
    await _file_row(pool, scope, "Memory file", memory_id)
    await _file_row(pool, scope, "Nested memory file", nested_id)

    resp = await client.get(
        "/api/v1/me/file-activity", params={"limit": 200}, headers=_auth(api_key)
    )
    assert resp.status_code == 200
    labels = [e["target_label"] for e in resp.json()["events"]]
    assert "Loose file" in labels
    assert "Memory file" not in labels
    assert "Nested memory file" not in labels


@pytest.mark.asyncio
async def test_file_activity_is_scope_only(client: AsyncClient, pool):
    """Home's feed shows the active scope and nothing else — content another
    scope shared with the caller belongs to the shared surfaces, not to this
    scope's home. A stash's home page must never show another stash's pages."""
    owner_key = await _register(client, "activity_mem_owner")
    friend_key = await _register(client, "activity_mem_friend")
    owner = UUID((await _scope(client, owner_key))["id"])
    friend = UUID((await _scope(client, friend_key))["id"])

    memory_id = (await client.get("/api/v1/me/memory-folder", headers=_auth(owner_key))).json()[
        "id"
    ]
    wiki = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Their wiki page", "content": "curated", "folder_id": memory_id},
        headers=_auth(owner_key),
    )
    assert wiki.status_code == 201
    plain = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Their shared page", "content": "hello"},
        headers=_auth(owner_key),
    )
    assert plain.status_code == 201
    for page_id in (wiki.json()["id"], plain.json()["id"]):
        await pool.execute(
            "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
            "principal_id, permission, created_by) VALUES ($1,'page',$2,'user',$3,'read',$1)",
            owner,
            UUID(page_id),
            friend,
        )

    resp = await client.get(
        "/api/v1/me/file-activity", params={"limit": 200}, headers=_auth(friend_key)
    )
    assert resp.status_code == 200
    labels = [e["target_label"] for e in resp.json()["events"]]
    # Even a real share doesn't put another scope's content on this home feed.
    assert "Their shared page" not in labels
    assert "Their wiki page" not in labels

    # In the owner's own scope the plain page shows and the Memory rule holds.
    own = await client.get(
        "/api/v1/me/file-activity", params={"limit": 200}, headers=_auth(owner_key)
    )
    own_labels = [e["target_label"] for e in own.json()["events"]]
    assert "Their shared page" in own_labels
    assert "Their wiki page" not in own_labels


@pytest.mark.asyncio
async def test_file_activity_paginates_with_before_cursor(client: AsyncClient):
    api_key = await _register(client, "activity_paged")
    for n in (1, 2, 3):
        r = await client.post(
            "/api/v1/me/pages/new",
            json={"name": f"paged-{n}", "content": "x"},
            headers=_auth(api_key),
        )
        assert r.status_code == 201

    # Page through one event at a time using the last event's ts as the cursor.
    seen: list[tuple[str, str, str]] = []
    before: str | None = None
    has_more = True
    while has_more:
        params: dict = {"limit": 1}
        if before:
            params["before"] = before
        resp = await client.get("/api/v1/me/file-activity", params=params, headers=_auth(api_key))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["events"]) == 1
        seen.extend((e["kind"], e["target_id"], e["ts"]) for e in body["events"])
        before = body["events"][-1]["ts"]
        has_more = body["has_more"]
        assert len(seen) <= 10, "cursor failed to advance"

    assert len(seen) == len(set(seen)), "an event repeated across pages"
    assert len(seen) == 3
