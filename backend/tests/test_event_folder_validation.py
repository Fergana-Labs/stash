"""Event uploads validate folder ownership, same as session/transcript uploads.

The events routes were the one write path where session_folder_id went
straight to the insert. Without the gate, any authenticated user could file
their session into a stranger's folder — polluting that folder's (possibly
public) listing and granting its owner read on the mis-filed session.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name
from .test_permissions import _auth, _register_with_email


async def _user(client: AsyncClient) -> str:
    api_key, _ = await _register_with_email(client, f"{unique_name('u')}@example.com")
    return api_key


async def _folder(client: AsyncClient, api_key: str) -> str:
    resp = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "Mine", "external_key": unique_name("key")},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _event(session_id: str, folder_id: str | None = None) -> dict:
    event = {
        "agent_name": "cli",
        "event_type": "user_message",
        "content": "hello",
        "session_id": session_id,
    }
    if folder_id is not None:
        event["session_folder_id"] = folder_id
    return event


@pytest.mark.asyncio
async def test_event_batch_rejects_foreign_folder(client: AsyncClient):
    victim_key = await _user(client)
    victim_folder = await _folder(client, victim_key)

    attacker_key = await _user(client)
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("attack-1", victim_folder)]},
        headers=_auth(attacker_key),
    )
    assert resp.status_code == 404

    # And nothing landed: the victim's folder stays empty.
    listing = await client.get(
        f"/api/v1/me/session-folders/{victim_folder}/sessions",
        headers=_auth(victim_key),
    )
    if listing.status_code == 200:
        assert listing.json() in ([], {"sessions": []})


@pytest.mark.asyncio
async def test_single_event_rejects_foreign_folder(client: AsyncClient):
    victim_key = await _user(client)
    victim_folder = await _folder(client, victim_key)

    attacker_key = await _user(client)
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json=_event("attack-2", victim_folder),
        headers=_auth(attacker_key),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_event_into_own_folder_still_works(client: AsyncClient):
    api_key = await _user(client)
    folder_id = await _folder(client, api_key)
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("own-1", folder_id)]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_read_key_can_get_or_create_folder(client: AsyncClient):
    """The read-key contract is 'full read + feed your own transcripts';
    resolving the folder to feed them into is step one of that flow."""
    api_key, _ = await _register_with_email(client, f"{unique_name('rk')}@example.com")
    minted = await client.post(
        "/api/v1/users/me/keys",
        json={"name": "agent", "access": "read"},
        headers=_auth(api_key),
    )
    assert minted.status_code in (200, 201), minted.text
    read_key = minted.json()["api_key"]

    resp = await client.post(
        "/api/v1/me/session-folders/get-or-create",
        json={"name": "Org X", "external_key": unique_name("orgx")},
        headers=_auth(read_key),
    )
    assert resp.status_code == 200, resp.text
