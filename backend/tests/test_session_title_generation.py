"""Tests for what the title generator treats as titleable session content."""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.tasks import session_titles as session_titles_task

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _make_session(client: AsyncClient, api_key: str, session_id: str) -> dict:
    scope_resp = await client.get("/api/v1/users/me", headers=_auth(api_key))
    assert scope_resp.status_code == 200

    session_resp = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": session_id, "agent_name": "claude"},
        headers=_auth(api_key),
    )
    assert session_resp.status_code == 201
    return scope_resp.json()


async def _add_event(pool, owner_user_id: str, session_id: str, event_type: str, content: str):
    await pool.execute(
        "INSERT INTO history_events "
        "(owner_user_id, session_id, agent_name, event_type, content, created_at) "
        "VALUES ($1, $2, 'claude', $3, $4, now())",
        owner_user_id,
        session_id,
        event_type,
        content,
    )


@pytest.mark.asyncio
async def test_session_end_marker_alone_is_not_worth_an_llm_call(
    client: AsyncClient, pool, monkeypatch
):
    """The hook ends every session, including ones where nothing happened.

    Titling that marker cost a model call per session and produced titles like
    "Empty Session" -- 4,064 of them in prod before this filter existed.
    """
    api_key = await _register(client)
    scope = await _make_session(client, api_key, "sess-title-marker-only")
    await _add_event(pool, scope["id"], "sess-title-marker-only", "session_end", "Session ended.")

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    async def _fail_if_called(source: str) -> str:
        raise AssertionError(f"the model was asked to title a marker: {source!r}")

    monkeypatch.setattr(session_titles_task, "_generate_title", _fail_if_called)

    result = await session_titles_task._generate_for_session(
        UUID(scope["id"]), "sess-title-marker-only"
    )

    assert result == "missing"
    row = await pool.fetchrow(
        "SELECT title FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
        scope["id"],
        "sess-title-marker-only",
    )
    assert row["title"] is None


@pytest.mark.asyncio
async def test_real_events_still_generate_without_the_marker_in_the_source(
    client: AsyncClient, pool, monkeypatch
):
    """A session with real content is still titled, and the marker is not part
    of what the model reads -- otherwise every transcript would end with
    boilerplate the title could latch onto."""
    api_key = await _register(client)
    scope = await _make_session(client, api_key, "sess-title-real-content")
    await _add_event(
        pool,
        scope["id"],
        "sess-title-real-content",
        "user_message",
        "fix the flaky auth test",
    )
    await _add_event(
        pool,
        scope["id"],
        "sess-title-real-content",
        "session_end",
        "Session ended. 2 tool uses.",
    )

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    seen: list[str] = []

    async def _capture(source: str) -> str:
        seen.append(source)
        return "Fix the flaky auth test"

    monkeypatch.setattr(session_titles_task, "_generate_title", _capture)

    result = await session_titles_task._generate_for_session(
        UUID(scope["id"]), "sess-title-real-content"
    )

    assert result == "generated"
    assert len(seen) == 1
    assert "fix the flaky auth test" in seen[0]
    assert "Session ended" not in seen[0]

    row = await pool.fetchrow(
        "SELECT title FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
        scope["id"],
        "sess-title-real-content",
    )
    assert row["title"] == "Fix the flaky auth test"


@pytest.mark.asyncio
async def test_reconcile_does_not_queue_marker_only_sessions(
    client: AsyncClient, pool, monkeypatch
):
    """The 60s reconcile is what re-sent the same untitled sessions every tick."""
    api_key = await _register(client)
    scope = await _make_session(client, api_key, "sess-title-reconcile-marker")
    await _add_event(
        pool,
        scope["id"],
        "sess-title-reconcile-marker",
        "session_end",
        "Imported historical session (27 KB)",
    )

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")

    queued: list[tuple] = []
    monkeypatch.setattr(
        session_titles_task.generate_session_title,
        "delay",
        lambda *args: queued.append(args),
    )

    await session_titles_task._reconcile_missing()

    assert ("sess-title-reconcile-marker",) not in [(a[1],) for a in queued]
