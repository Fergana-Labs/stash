"""A session rating is the user's own good/bad verdict on a trace. It must
round-trip through the detail and list payloads (that is how the viewer and
the list show it), be clearable, and reject anything outside good/bad."""

import pytest
from httpx import AsyncClient

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


async def _session_with_event(client: AsyncClient, api_key: str, session_id: str) -> None:
    created = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": session_id, "agent_name": "claude"},
        headers=_auth(api_key),
    )
    assert created.status_code == 201
    event = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "session_id": session_id,
            "event_type": "user_message",
            "content": "Fix the flaky test",
            "agent_name": "claude",
            "created_at": "2026-01-02T00:00:00Z",
            "metadata": {"model": "claude-sonnet-4-6"},
        },
        headers=_auth(api_key),
    )
    assert event.status_code == 201, event.text


@pytest.mark.asyncio
async def test_rating_round_trips_through_detail_and_list(client: AsyncClient):
    key = await _register(client)
    await _session_with_event(client, key, "sess-rate-1")

    detail = await client.get(
        "/api/v1/me/sessions/detail?session_id=sess-rate-1", headers=_auth(key)
    )
    assert detail.json()["rating"] is None

    resp = await client.patch(
        "/api/v1/me/sessions/rating?session_id=sess-rate-1",
        json={"rating": "good"},
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"rating": "good"}

    detail = await client.get(
        "/api/v1/me/sessions/detail?session_id=sess-rate-1", headers=_auth(key)
    )
    assert detail.json()["rating"] == "good"

    listed = await client.get("/api/v1/me/sessions", headers=_auth(key))
    [row] = [s for s in listed.json()["sessions"] if s["session_id"] == "sess-rate-1"]
    assert row["rating"] == "good"


@pytest.mark.asyncio
async def test_rating_can_be_cleared(client: AsyncClient):
    key = await _register(client)
    await _session_with_event(client, key, "sess-rate-2")
    await client.patch(
        "/api/v1/me/sessions/rating?session_id=sess-rate-2",
        json={"rating": "bad"},
        headers=_auth(key),
    )
    resp = await client.patch(
        "/api/v1/me/sessions/rating?session_id=sess-rate-2",
        json={"rating": None},
        headers=_auth(key),
    )
    assert resp.status_code == 200
    detail = await client.get(
        "/api/v1/me/sessions/detail?session_id=sess-rate-2", headers=_auth(key)
    )
    assert detail.json()["rating"] is None


@pytest.mark.asyncio
async def test_rating_outside_good_bad_is_rejected(client: AsyncClient):
    key = await _register(client)
    await _session_with_event(client, key, "sess-rate-3")
    resp = await client.patch(
        "/api/v1/me/sessions/rating?session_id=sess-rate-3",
        json={"rating": "meh"},
        headers=_auth(key),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rating_a_missing_session_is_404(client: AsyncClient):
    key = await _register(client)
    resp = await client.patch(
        "/api/v1/me/sessions/rating?session_id=nope",
        json={"rating": "good"},
        headers=_auth(key),
    )
    assert resp.status_code == 404
