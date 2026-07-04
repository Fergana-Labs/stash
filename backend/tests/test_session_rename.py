"""Tests for the PATCH /sessions/{session_id}/title endpoint."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name or unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _make_scope_with_session(client: AsyncClient, api_key: str, session_id: str):
    scope_resp = await client.get(
        "/api/v1/users/me",
        headers=_auth(api_key),
    )
    assert scope_resp.status_code == 200
    scope = scope_resp.json()

    session_resp = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": session_id, "agent_name": "claude"},
        headers=_auth(api_key),
    )
    assert session_resp.status_code == 201
    return scope, session_resp.json()


@pytest.mark.asyncio
async def test_rename_session_persists_title(client: AsyncClient, pool):
    api_key, _user = await _register(client)
    scope, _session = await _make_scope_with_session(client, api_key, "sess-rename-1")

    resp = await client.patch(
        "/api/v1/me/sessions/sess-rename-1/title",
        json={"title": "  Investigate flaky auth test  "},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json() == {"title": "Investigate flaky auth test"}

    get_resp = await client.get(
        "/api/v1/me/sessions/sess-rename-1",
        headers=_auth(api_key),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Investigate flaky auth test"

    row = await pool.fetchrow(
        "SELECT title, user_set FROM session_titles WHERE owner_user_id = $1 AND session_id = $2",
        scope["id"],
        "sess-rename-1",
    )
    assert row["title"] == "Investigate flaky auth test"
    assert row["user_set"] is True


@pytest.mark.asyncio
async def test_rename_session_truncates_overlong_title(client: AsyncClient, pool):
    api_key, _user = await _register(client)
    _scope, _session = await _make_scope_with_session(client, api_key, "sess-rename-2")

    long_title = "a" * 200
    resp = await client.patch(
        "/api/v1/me/sessions/sess-rename-2/title",
        json={"title": long_title},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    # MAX_TITLE_LENGTH from the service is 80
    assert len(resp.json()["title"]) == 80


@pytest.mark.asyncio
async def test_rename_session_rejects_empty_title(client: AsyncClient):
    api_key, _user = await _register(client)
    _scope, _session = await _make_scope_with_session(client, api_key, "sess-rename-3")

    resp = await client.patch(
        "/api/v1/me/sessions/sess-rename-3/title",
        json={"title": "   "},
        headers=_auth(api_key),
    )
    # Pydantic accepts whitespace (it's not empty), but the service rejects it
    # once trimmed. Both 422 (Pydantic) and 422 (HTTPException) are acceptable.
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rename_session_rejects_unknown_session(client: AsyncClient):
    api_key, _user = await _register(client)
    _scope, _session = await _make_scope_with_session(client, api_key, "sess-rename-4")

    resp = await client.patch(
        "/api/v1/me/sessions/does-not-exist/title",
        json={"title": "noop"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rename_session_blocks_non_owner(client: AsyncClient):
    owner_key, _owner = await _register(client)
    _scope, _session = await _make_scope_with_session(client, owner_key, "sess-rename-5")

    outsider_key, _outsider = await _register(client)
    resp = await client.patch(
        "/api/v1/me/sessions/sess-rename-5/title",
        json={"title": "should not stick"},
        headers=_auth(outsider_key),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_user_set_title_survives_auto_regeneration(client: AsyncClient, pool):
    """A manual rename must not be overwritten by the title-generation task."""
    from uuid import UUID

    from backend.tasks import session_titles as session_titles_task

    api_key, _user = await _register(client)
    scope, _session = await _make_scope_with_session(client, api_key, "sess-rename-6")

    # Seed an event so the generator sees content to work with.
    await pool.execute(
        "INSERT INTO history_events "
        "(owner_user_id, session_id, agent_name, event_type, content, created_at) "
        "VALUES ($1, $2, 'claude', 'user_message', 'first prompt', now())",
        scope["id"],
        "sess-rename-6",
    )

    rename_resp = await client.patch(
        "/api/v1/me/sessions/sess-rename-6/title",
        json={"title": "User wrote this"},
        headers=_auth(api_key),
    )
    assert rename_resp.status_code == 200

    # Run the generator directly. Real prod path goes through Celery but the
    # body is the same coroutine.
    result = await session_titles_task._generate_for_session(
        UUID(scope["id"]),
        "sess-rename-6",
    )
    assert result == "user-set"

    row = await pool.fetchrow(
        "SELECT title, user_set FROM session_titles WHERE owner_user_id = $1 AND session_id = $2",
        scope["id"],
        "sess-rename-6",
    )
    assert row["title"] == "User wrote this"
    assert row["user_set"] is True
