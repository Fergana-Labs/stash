"""The Session Analytics endpoint aggregates the same sessions the list shows.

Two rules matter enough to pin: the response shape the dashboard renders
(totals / per_day / by_agent / by_person), and the agent-name suppression the
sessions list already applies — the CLI historically defaulted agent_name to
the author's login handle, so a session "by" your own handle is a person's
session, not an agent's, and must not appear in the agent breakdown.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient, name: str) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


async def _push_event(
    client: AsyncClient, api_key: str, session_id: str, agent_name: str, content: str
) -> None:
    resp = await client.post(
        "/api/v1/me/sessions/events",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "agent_name": agent_name,
            "event_type": "user_message",
            "content": content,
            "session_id": session_id,
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_sessions_analytics_shape_and_agent_suppression(client: AsyncClient):
    login = unique_name()
    api_key = await _register(client, login)

    # One real agent session (two events), and one whose agent_name is the
    # author's own login handle — the CLI's old default, not an agent.
    await _push_event(client, api_key, "claude-abc", "claude", "fix the tests")
    await _push_event(client, api_key, "claude-abc", "claude", "done")
    await _push_event(client, api_key, "manual-xyz", login, "poking around by hand")

    resp = await client.get(
        "/api/v1/me/sessions/analytics",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["totals"] == {"sessions": 2, "events": 3}

    # 60 daily buckets, today last, and both sessions landed today.
    assert len(data["per_day"]) == 60
    assert all(set(d) == {"day", "sessions"} for d in data["per_day"])
    assert sum(d["sessions"] for d in data["per_day"]) == 2
    assert data["per_day"][-1]["sessions"] == 2

    # The handle-named session counts toward no agent; the person gets both.
    assert data["by_agent"] == [{"agent": "claude", "sessions": 1}]
    assert data["by_person"] == [{"name": login, "sessions": 2}]


@pytest.mark.asyncio
async def test_sessions_analytics_excludes_other_users(client: AsyncClient):
    mine = await _register(client, unique_name())
    theirs = await _register(client, unique_name())
    await _push_event(client, theirs, "claude-other", "claude", "someone else's work")

    resp = await client.get(
        "/api/v1/me/sessions/analytics",
        headers={"Authorization": f"Bearer {mine}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"] == {"sessions": 0, "events": 0}
    assert data["by_agent"] == []
    assert data["by_person"] == []
