"""Tests for history event cursor pagination."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("hist"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


async def _workspace(client: AsyncClient, api_key: str) -> dict:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "History pagination"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


async def _seed_events(client: AsyncClient, api_key: str, owner_user_id: str) -> None:
    headers = _auth(api_key)
    for day in range(1, 4):
        resp = await client.post(
            f"/api/v1/workspaces/{owner_user_id}/sessions/events",
            json={
                "agent_name": "tester",
                "event_type": "note",
                "content": f"event-{day}",
                "session_id": "pagination-session",
                "created_at": f"2026-01-0{day}T00:00:00Z",
            },
            headers=headers,
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_workspace_history_before_and_after_cursors(client: AsyncClient):
    api_key = await _register(client)
    ws = await _workspace(client, api_key)
    headers = _auth(api_key)
    await _seed_events(client, api_key, ws["id"])

    first = await client.get(
        f"/api/v1/workspaces/{ws['id']}/sessions/events",
        params={"limit": 2},
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert [e["content"] for e in first_body["events"]] == ["event-3", "event-2"]
    assert first_body["has_more"] is True

    older = await client.get(
        f"/api/v1/workspaces/{ws['id']}/sessions/events",
        params={"limit": 2, "before": first_body["events"][-1]["created_at"]},
        headers=headers,
    )
    assert older.status_code == 200
    older_body = older.json()
    assert [e["content"] for e in older_body["events"]] == ["event-1"]
    assert older_body["has_more"] is False

    asc = await client.get(
        f"/api/v1/workspaces/{ws['id']}/sessions/events",
        params={"limit": 2, "order": "asc"},
        headers=headers,
    )
    assert asc.status_code == 200
    asc_body = asc.json()
    assert [e["content"] for e in asc_body["events"]] == ["event-1", "event-2"]

    newer = await client.get(
        f"/api/v1/workspaces/{ws['id']}/sessions/events",
        params={"limit": 2, "order": "asc", "after": asc_body["events"][-1]["created_at"]},
        headers=headers,
    )
    assert newer.status_code == 200
    assert [e["content"] for e in newer.json()["events"]] == ["event-3"]


@pytest.mark.asyncio
async def test_all_history_events_before_cursor(client: AsyncClient):
    api_key = await _register(client)
    ws = await _workspace(client, api_key)
    headers = _auth(api_key)
    await _seed_events(client, api_key, ws["id"])

    first = await client.get(
        "/api/v1/me/session-events",
        params={"limit": 2},
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert [e["content"] for e in first_body["events"]] == ["event-3", "event-2"]
    assert first_body["has_more"] is True

    older = await client.get(
        "/api/v1/me/session-events",
        params={"limit": 2, "before": first_body["events"][-1]["created_at"]},
        headers=headers,
    )
    assert older.status_code == 200
    older_body = older.json()
    assert [e["content"] for e in older_body["events"]] == ["event-1"]
    assert older_body["has_more"] is False
