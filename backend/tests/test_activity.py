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
        f"/api/v1/workspaces/{workspace_id}/sessions/events",
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
    workspace = await _workspace(client, api_key, "Timeline Workspace")

    for content in ("first event", "second event"):
        event_resp = await client.post(
            f"/api/v1/workspaces/{workspace['id']}/sessions/events",
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
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={"name": "Not a contributor", "content": "page content"},
        headers=_auth(api_key),
    )
    assert page_resp.status_code == 201

    resp = await client.get(
        "/api/v1/me/activity-timeline",
        params={"days": 365, "workspace_id": workspace["id"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    timeline = resp.json()
    assert timeline["contributors"] == ["Timeline Human / codex"]
    assert "Pages" not in timeline["contributors"]

    totals = [
        contributor["total"]
        for bucket in timeline["buckets"]
        for contributor in bucket["contributors"].values()
    ]
    assert totals == [1]


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
    assert visible[0]["workspace_id"] == owner_workspace["id"]
    assert visible[0]["workspace_name"] == "Team Activity"
    assert "stash_id" not in visible[0]
    assert "stash_name" not in visible[0]
    assert visible[0]["target_label"] == "tester: visible-session"
    assert hidden == []


@pytest.mark.asyncio
async def test_user_activity_can_filter_to_one_workspace(client: AsyncClient):
    api_key = await _register(client, "activity_filter")
    first_workspace = await _workspace(client, api_key, "First Activity")
    second_workspace = await _workspace(client, api_key, "Second Activity")

    await _event(client, api_key, first_workspace["id"], "first-session")
    await _event(client, api_key, second_workspace["id"], "second-session")

    resp = await client.get(
        "/api/v1/me/activity",
        params={"limit": 200, "workspace_id": first_workspace["id"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200

    events = [event for event in resp.json() if event["kind"] == "session.uploaded"]
    assert {event["target_id"] for event in events} == {"first-session"}
    assert {event["workspace_id"] for event in events} == {first_workspace["id"]}
