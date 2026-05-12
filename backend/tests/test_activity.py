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


async def _workspace(client: AsyncClient, api_key: str, name: str) -> dict:
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": name},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201
    return resp.json()


async def _event(client: AsyncClient, api_key: str, workspace_id: str, session_id: str) -> None:
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/memory/events",
        json={
            "agent_name": "tester",
            "event_type": "assistant_message",
            "content": session_id,
            "session_id": session_id,
            "created_at": "2026-01-02T00:00:00Z",
        },
        headers=_auth(api_key),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_user_activity_is_scoped_to_accessible_workspaces(client: AsyncClient):
    owner_key = await _register(client, "activity_owner")
    other_key = await _register(client, "activity_other")
    owner_workspace = await _workspace(client, owner_key, "Team Activity")
    other_workspace = await _workspace(client, other_key, "Hidden Activity")

    await _event(client, owner_key, owner_workspace["id"], "visible-session")
    await _event(client, other_key, other_workspace["id"], "hidden-session")

    resp = await client.get(
        "/api/v1/me/activity",
        params={"limit": 200},
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200

    events = resp.json()
    visible = [
        event
        for event in events
        if event["kind"] == "session.uploaded" and event["target_id"] == "visible-session"
    ]
    hidden = [
        event
        for event in events
        if event["kind"] == "session.uploaded" and event["target_id"] == "hidden-session"
    ]

    assert len(visible) == 1
    assert visible[0]["stash_id"] == owner_workspace["id"]
    assert visible[0]["stash_name"] == "Team Activity"
    assert visible[0]["target_label"] == "tester: visible-session"
    assert hidden == []
