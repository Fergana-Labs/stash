import json
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

import numpy as np
import pytest
from httpx import AsyncClient

from backend.services import analytics_service, embeddings

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
    event_type: str = "assistant_message",
    model: str = "claude-sonnet-4-6",
    client_name: str | None = None,
) -> None:
    metadata = {"model": model}
    if client_name is not None:
        metadata["client"] = client_name
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": agent_name,
            "event_type": event_type,
            "content": session_id,
            "session_id": session_id,
            "created_at": created_at,
            "metadata": metadata,
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
        "clusters": [],
        "stats": {"total_embeddings": 0, "projected": 0},
        "cached": False,
    }


@pytest.mark.asyncio
async def test_user_wide_embedding_projection_serves_cache_while_access_unchanged(
    client: AsyncClient,
    pool,
):
    """The memory page's embeddings map must come from the cache, not an
    inline UMAP fit — recomputing per load is the minute-long-render bug.
    The row is only trusted while its scope and embedding-space signatures
    still match."""
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
        "cluster": 0,
    }
    clusters = [{"index": 0, "name": "Roadmap", "size": 1}]
    await pool.execute(
        "INSERT INTO embedding_projections "
        "(user_id, source_type, owner_user_id, points, clusters, "
        " embedding_count, scope_signature, embedding_space, computed_at) "
        "VALUES ($1, '_all', NULL, $2, $3, 0, $4, $5, now())",
        user_id,
        [point],
        clusters,
        await analytics_service.scope_signature(user_id),
        embeddings.space_id(),
    )

    projection = await client.get(
        "/api/v1/me/embedding-projection",
        headers=_auth(body["api_key"]),
    )

    assert projection.status_code == 200
    assert projection.json() == {
        "points": [point],
        "clusters": clusters,
        "stats": {"total_embeddings": 0, "projected": 1},
        "cached": True,
    }


@pytest.mark.asyncio
async def test_embedding_projection_plots_one_point_per_session(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    """Session themes plot one point per transcript and represent it only by
    user prompts. Assistant prose and tool output describe execution rather
    than intent, so including them makes clusters reflect harness behavior."""

    async def keyword_names_only(labels_per_cluster, keyword_names):
        return keyword_names

    monkeypatch.setattr(analytics_service, "concept_names", keyword_names_only)

    api_key = await _register(client, "session_points")
    scope = await _scope(client, api_key)

    await _event(client, api_key, scope["id"], "session-a", event_type="user_message")
    await _event(
        client,
        api_key,
        scope["id"],
        "session-a",
        created_at="2026-01-02T01:00:00Z",
        event_type="user_message",
    )
    await _event(client, api_key, scope["id"], "session-b", event_type="user_message")
    await _event(client, api_key, scope["id"], "session-b", event_type="assistant_message")

    await pool.execute(
        "UPDATE history_events SET embedding = $1 WHERE session_id = 'session-a'",
        np.full(384, 0.5, dtype=np.float32),
    )
    await pool.execute(
        "UPDATE history_events SET embedding = $1 WHERE session_id = 'session-b'",
        np.full(384, -0.5, dtype=np.float32),
    )
    await pool.execute(
        "UPDATE sessions SET title = 'Billing webhook fixes' WHERE session_id = 'session-a'"
    )

    resp = await client.get("/api/v1/me/embedding-projection", headers=_auth(api_key))

    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["total_embeddings"] == 2
    points = {p["id"]: p for p in body["points"]}
    assert set(points) == {"session-a", "session-b"}
    assert all(p["source"] == "sessions" for p in points.values())

    # Detail counts prompts, not every transcript event.
    assert points["session-a"]["label"] == "Billing webhook fixes"
    assert points["session-a"]["detail"] == "2 prompts · tester"
    assert points["session-b"]["label"] == "session-b"
    assert points["session-b"]["detail"] == "1 prompt · tester"


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
async def test_recent_activity_contains_sessions_and_new_skills_not_page_edits(client: AsyncClient):
    owner_key = await _register(client, "activity_owner")
    scope = await _scope(client, owner_key)
    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Not Home activity", "content": "hello"},
        headers=_auth(owner_key),
    )
    await _event(client, owner_key, scope["id"], "recent-session", agent_name="codex")
    skill = await client.post(
        "/api/v1/me/skills/new",
        json={"name": "Recent Skill", "description": "Use for recent activity tests."},
        headers=_auth(owner_key),
    )
    assert skill.status_code == 201

    resp = await client.get(
        "/api/v1/me/recent-activity", params={"limit": 20}, headers=_auth(owner_key)
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert {event["kind"] for event in events} == {"session", "skill.created"}
    assert {event["title"] for event in events} == {"recent-session", "Recent Skill"}
    session = next(event for event in events if event["kind"] == "session")
    skill_event = next(event for event in events if event["kind"] == "skill.created")
    assert session["subtitle"].endswith("'s claude-sonnet-4-6")
    assert skill_event["subtitle"] == "New Skill"
    assert all("Not Home activity" not in event["title"] for event in events)


async def _file_row(pool, owner_user_id: UUID, name: str, folder_id: UUID | None) -> None:
    await pool.execute(
        "INSERT INTO files (owner_user_id, name, content_type, size_bytes, storage_key, "
        "uploaded_by, folder_id) VALUES ($1, $2, 'image/png', 9, $2, $1, $3)",
        owner_user_id,
        name,
        folder_id,
    )


@pytest.mark.asyncio
async def test_recent_activity_ignores_file_uploads(client: AsyncClient, pool):
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
        "/api/v1/me/recent-activity", params={"limit": 20}, headers=_auth(api_key)
    )
    assert resp.status_code == 200
    assert resp.json()["events"] == []


@pytest.mark.asyncio
async def test_recent_activity_ignores_page_sharing(client: AsyncClient, pool):
    """Home's feed answers "what landed in THIS stash", so a page another user
    shared with the caller — readable everywhere else — must not appear: it is
    that scope's activity, not the caller's."""
    owner_key = await _register(client, "activity_mem_owner")
    friend_key = await _register(client, "activity_mem_friend")
    owner = UUID((await _scope(client, owner_key))["id"])
    friend = UUID((await _scope(client, friend_key))["id"])

    plain = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Their shared page", "content": "hello"},
        headers=_auth(owner_key),
    )
    assert plain.status_code == 201
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,'page',$2,'user',$3,'read',$1)",
        owner,
        UUID(plain.json()["id"]),
        friend,
    )
    mine = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "My own page", "content": "hi"},
        headers=_auth(friend_key),
    )
    assert mine.status_code == 201

    resp = await client.get(
        "/api/v1/me/recent-activity", params={"limit": 20}, headers=_auth(friend_key)
    )
    assert resp.status_code == 200
    assert resp.json()["events"] == []


@pytest.mark.asyncio
async def test_recent_activity_returns_only_the_requested_latest_sessions(client: AsyncClient):
    api_key = await _register(client, "activity_paged")
    scope = await _scope(client, api_key)
    for n in (1, 2, 3):
        await _event(
            client,
            api_key,
            scope["id"],
            f"session-{n}",
            created_at=f"2026-01-0{n}T00:00:00Z",
        )

    resp = await client.get(
        "/api/v1/me/recent-activity", params={"limit": 2}, headers=_auth(api_key)
    )
    assert resp.status_code == 200
    assert [event["title"] for event in resp.json()["events"]] == ["session-3", "session-2"]


@pytest.mark.asyncio
async def test_upload_sources_pair_coding_agent_with_uploader_computer(client: AsyncClient, pool):
    api_key = await _register(client, "upload_sources")
    scope = await _scope(client, api_key)
    await pool.execute(
        "UPDATE user_api_keys SET name = 'CLI (henrys-macbook-pro)', key_type = 'cli' "
        "WHERE user_id = $1",
        UUID(scope["id"]),
    )
    await pool.execute(
        """
        INSERT INTO user_api_keys (user_id, key_hash, name, key_type)
        VALUES ($1, 'unused-machine-key', 'CLI (henrys-mac-mini)', 'cli')
        """,
        UUID(scope["id"]),
    )
    await pool.execute(
        """
        INSERT INTO user_api_keys (user_id, key_hash, name, key_type)
        VALUES ($1, 'unused-sprite-key', 'local sprite', 'machine')
        """,
        UUID(scope["id"]),
    )
    await _event(
        client,
        api_key,
        scope["id"],
        "codex-session",
        client_name="codex_cli",
    )

    resp = await client.get("/api/v1/me/upload-sources", headers=_auth(api_key))
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert len(sources) == 2
    assert sources[0]["key_id"]
    assert {key: value for key, value in sources[0].items() if key != "key_id"} == {
        "client": "codex_cli",
        "key_name": "CLI (henrys-macbook-pro)",
        "uploads_enabled": True,
        "can_manage": True,
        "session_count": 1,
        "last_uploaded_at": "2026-01-02T00:00:00+00:00",
    }
    assert {key: value for key, value in sources[1].items() if key != "key_id"} == {
        "client": None,
        "key_name": "CLI (henrys-mac-mini)",
        "uploads_enabled": True,
        "can_manage": True,
        "session_count": 0,
        "last_uploaded_at": None,
    }

    key_id = sources[0]["key_id"]
    resp = await client.patch(
        f"/api/v1/me/upload-sources/{key_id}",
        json={"uploads_enabled": False},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    blocked = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "codex",
            "event_type": "assistant_message",
            "content": "blocked",
            "session_id": "blocked-session",
            "metadata": {"client": "codex_cli"},
        },
        headers=_auth(api_key),
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Uploads are disabled for this installation"
