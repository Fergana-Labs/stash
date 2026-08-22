"""Resolving the names a session actually answers to.

Search names session hits by title and the VFS lists them by title, so a
handle arriving from either is a title in the VFS's spelling — including the
`--<id>` suffix the VFS adds when two sessions share one. Every name shown to
an agent has to be a name that resolves, or the agent is pushed back onto ids.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name

RESOLVE = "/api/v1/me/sessions/resolve"


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
        f"/api/v1/me/sessions/title?session_id={session_id}",
        headers=_auth(api_key),
        json={"title": title},
    )
    assert renamed.status_code == 200
    detail = await client.get(
        f"/api/v1/me/sessions/detail?session_id={session_id}", headers=_auth(api_key)
    )
    assert detail.status_code == 200
    return detail.json()


@pytest.mark.asyncio
async def test_a_title_resolves_in_stored_and_vfs_spellings(client: AsyncClient):
    api_key = await _register(client)
    await _titled_session(client, api_key, "claude-ref-1", 'Ship the "fast" path')

    for handle in ('Ship the "fast" path', "Ship the fast path"):
        resolved = await client.get(RESOLVE, params={"ref": handle}, headers=_auth(api_key))
        assert resolved.status_code == 200, handle
        body = resolved.json()
        assert body["matched"] is True, handle
        assert body["session_id"] == "claude-ref-1", handle


@pytest.mark.asyncio
async def test_an_unmatched_handle_echoes_back_as_an_id(client: AsyncClient):
    """A handle naming no title is already an id. Echoing it keeps every
    caller on one codepath — ask, then use the answer."""
    api_key = await _register(client)
    await _titled_session(client, api_key, "claude-ref-2", "Something real")

    resolved = await client.get(RESOLVE, params={"ref": "claude-ref-2"}, headers=_auth(api_key))
    assert resolved.json()["session_id"] == "claude-ref-2"

    unknown = await client.get(RESOLVE, params={"ref": "not-a-session"}, headers=_auth(api_key))
    assert unknown.status_code == 200
    assert unknown.json() == {
        "ref": "not-a-session",
        "matched": False,
        "session_id": "not-a-session",
        "id": "not-a-session",
        "title": None,
        "name": None,
    }


@pytest.mark.asyncio
async def test_the_suffixed_vfs_name_of_a_duplicated_title_resolves(client: AsyncClient):
    """Two sessions can share a title; the VFS separates them as
    `<title>--<id8>`. That name is what `ls /sessions` shows, so it has to
    resolve — otherwise the only name an agent can see is unusable."""
    api_key = await _register(client)
    first = await _titled_session(client, api_key, "claude-dup-a", "Nightly deploy")
    second = await _titled_session(client, api_key, "claude-dup-b", "Nightly deploy")

    clash = await client.get(RESOLVE, params={"ref": "Nightly deploy"}, headers=_auth(api_key))
    assert clash.status_code == 409
    detail = clash.json()["detail"]

    suffixed = sorted(f"Nightly deploy--{str(session['id'])[:8]}" for session in (first, second))
    for name in suffixed:
        assert name in detail, detail

    resolved_ids = set()
    for name in suffixed:
        one = await client.get(RESOLVE, params={"ref": name}, headers=_auth(api_key))
        assert one.status_code == 200, name
        assert one.json()["matched"] is True, name
        resolved_ids.add(one.json()["session_id"])
    assert resolved_ids == {"claude-dup-a", "claude-dup-b"}


@pytest.mark.asyncio
async def test_another_users_session_never_resolves(client: AsyncClient):
    api_key = await _register(client)
    await _titled_session(client, api_key, "claude-private", "Private planning notes")

    stranger = await _register(client)
    denied = await client.get(
        RESOLVE, params={"ref": "Private planning notes"}, headers=_auth(stranger)
    )
    # Not theirs to see: it falls through as an unmatched handle rather than
    # confirming a session by that name exists.
    assert denied.status_code == 200
    assert denied.json()["matched"] is False


@pytest.mark.asyncio
async def test_trashed_sessions_resolve_only_against_the_trash(client: AsyncClient):
    api_key = await _register(client)
    session = await _titled_session(client, api_key, "claude-trash-ref", "Abandoned refactor")
    await client.delete(f"/api/v1/me/sessions/{session['id']}", headers=_auth(api_key))

    live = await client.get(RESOLVE, params={"ref": "Abandoned refactor"}, headers=_auth(api_key))
    assert live.json()["matched"] is False

    trashed = await client.get(
        RESOLVE,
        params={"ref": "Abandoned refactor", "trashed": "true"},
        headers=_auth(api_key),
    )
    assert trashed.status_code == 200
    assert trashed.json()["matched"] is True
    assert trashed.json()["id"] == session["id"]


@pytest.mark.asyncio
async def test_reading_a_session_source_doc_by_title(client: AsyncClient):
    """stash_read_source / the sources API take the same handle, so an agent
    that found a session by title can read it without ever seeing an id."""
    api_key = await _register(client)
    await _titled_session(client, api_key, "claude-doc-1", "Refactor the importer")

    doc = await client.get(
        "/api/v1/me/sources/sessions/doc",
        params={"ref": "Refactor the importer"},
        headers=_auth(api_key),
    )
    assert doc.status_code == 200
    assert doc.json()["session"] == "claude-doc-1"
