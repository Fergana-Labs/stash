"""The trash names a session the way every other listing does — by its title.

`stash restore session:"<title>"` matches against this listing, so a session
printed here under its raw session_id would be named something no other
surface uses and nothing the user could type back.
"""

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


async def _titled_session(client: AsyncClient, api_key: str, session_id: str, title: str) -> dict:
    pushed = await client.post(
        "/api/v1/me/sessions/events",
        headers=_auth(api_key),
        json={
            "agent_name": "claude",
            "event_type": "user_message",
            "content": f"first prompt of {session_id}",
            "session_id": session_id,
        },
    )
    assert pushed.status_code == 201
    renamed = await client.patch(
        f"/api/v1/me/sessions/{session_id}/title",
        headers=_auth(api_key),
        json={"title": title},
    )
    assert renamed.status_code == 200
    detail = await client.get(f"/api/v1/me/sessions/{session_id}", headers=_auth(api_key))
    assert detail.status_code == 200
    return detail.json()


@pytest.mark.asyncio
async def test_trashed_session_is_named_by_its_title(client: AsyncClient):
    api_key = await _register(client)
    session = await _titled_session(
        client, api_key, "claude-trash-title", 'Abandoned "big" refactor'
    )

    trashed = await client.delete(f"/api/v1/me/sessions/{session['id']}", headers=_auth(api_key))
    assert trashed.status_code in (200, 204)

    listed = await client.get("/api/v1/me/trash", headers=_auth(api_key))
    assert listed.status_code == 200
    rows = listed.json()["sessions"]
    assert [r["name"] for r in rows] == ['Abandoned "big" refactor']
    # The row id is what `stash restore` ends up sending.
    assert rows[0]["id"] == session["id"]


@pytest.mark.asyncio
async def test_untitled_trashed_session_falls_back_to_its_session_id(client: AsyncClient):
    """A session whose title has not been generated yet is named by its id
    everywhere, so the trash agrees rather than rendering an empty name."""
    api_key = await _register(client)
    pushed = await client.post(
        "/api/v1/me/sessions/events",
        headers=_auth(api_key),
        json={
            "agent_name": "claude",
            "event_type": "user_message",
            "content": "no title generated for this one",
            "session_id": "claude-untitled",
        },
    )
    assert pushed.status_code == 201
    detail = await client.get("/api/v1/me/sessions/claude-untitled", headers=_auth(api_key))
    assert detail.status_code == 200

    await client.delete(f"/api/v1/me/sessions/{detail.json()['id']}", headers=_auth(api_key))

    listed = await client.get("/api/v1/me/trash", headers=_auth(api_key))
    names = [r["name"] for r in listed.json()["sessions"]]
    assert names and all(name for name in names), names
