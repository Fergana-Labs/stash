"""get-or-create session folders: the folder-per-org path for machine callers.

A customer app (e.g. Heavi) resolves one folder per org on every uploaded
turn. The endpoint must be idempotent under concurrency — folder names are
not unique, so a list-then-create client race would mint duplicate folders —
and the batch events endpoint must honor the resolved folder id so sessions
are born into it.
"""

import asyncio

import pytest
from httpx import AsyncClient

from .conftest import unique_name


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient, prefix: str) -> str:
    name = unique_name(prefix)
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1", "email": f"{name}@test.local"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(client: AsyncClient, _db_pool):
    key = await _register(client, "goc-idem")

    first = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "riverside-truck-parts"},
        headers=_auth(key),
    )
    assert first.status_code == 200
    again = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "riverside-truck-parts"},
        headers=_auth(key),
    )
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]

    other = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "acme-diesel"},
        headers=_auth(key),
    )
    assert other.json()["id"] != first.json()["id"]


@pytest.mark.asyncio
async def test_concurrent_calls_create_exactly_one_folder(client: AsyncClient, pool):
    """The whole point of the endpoint: two orgs' first turns arriving at the
    same moment must not mint duplicate folders."""
    key = await _register(client, "goc-race")

    responses = await asyncio.gather(
        *(
            client.post(
                "/api/v1/me/session-folders/get-or-create",
                json={"name": "same-org"},
                headers=_auth(key),
            )
            for _ in range(5)
        )
    )
    ids = {r.json()["id"] for r in responses}
    assert all(r.status_code == 200 for r in responses)
    assert len(ids) == 1

    count = await pool.fetchval("SELECT COUNT(*) FROM session_folders WHERE name = 'same-org'")
    assert count == 1


@pytest.mark.asyncio
async def test_blank_name_rejected(client: AsyncClient, _db_pool):
    key = await _register(client, "goc-blank")
    resp = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "   "},
        headers=_auth(key),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_batch_events_honor_session_folder_id(client: AsyncClient, pool):
    """Regression: the batch path used to drop session_folder_id, so every
    batch-pushed session landed in Default regardless of the request."""
    key = await _register(client, "goc-batch")

    folder = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "riverside-truck-parts"},
        headers=_auth(key),
    )
    folder_id = folder.json()["id"]

    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "heavi-chat",
                    "event_type": "user_message",
                    "content": "Need a fan clutch",
                    "session_id": "conv-folder-test",
                    "session_folder_id": folder_id,
                }
            ]
        },
        headers=_auth(key),
    )
    assert resp.status_code == 201

    stored = await pool.fetchval(
        "SELECT session_folder_id FROM sessions WHERE session_id = 'conv-folder-test'"
    )
    assert str(stored) == folder_id
