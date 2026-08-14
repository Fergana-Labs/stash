"""Stashes: extra isolated scopes owned by one user.

What matters here:
- A stash is a hermetic scope: content created inside it never appears in the
  personal scope's listings, and vice versa.
- Only the owner may enter the scope: the X-Stash-Scope header re-roots
  content routes for the owner and hard-403s everyone else.
- Ownership IS ownership: unlike a workspace member, the human owner keeps
  owner-only powers (sharing) over stash content.
- A key minted on the stash acts inside the stash with no header at all —
  the credential is the stash selector.
- The per-user cap fails loud with 409, never silently drops a stash.
"""

import uuid

import pytest
from httpx import AsyncClient

from ..services import stash_service
from .conftest import unique_name
from .test_permissions import _auth, _register_with_email


async def _register(client: AsyncClient) -> tuple[str, dict]:
    return await _register_with_email(client, f"{unique_name()}@example.com")


async def _create_stash(client: AsyncClient, api_key: str, name: str = "Work") -> dict:
    resp = await client.post("/api/v1/me/stashes", json={"name": name}, headers=_auth(api_key))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scoped(api_key: str, scope_user_id: str) -> dict:
    return {**_auth(api_key), "X-Stash-Scope": scope_user_id}


# --- Creation and listing ---


@pytest.mark.asyncio
async def test_create_and_list_stashes(client: AsyncClient):
    api_key, _ = await _register(client)
    stash = await _create_stash(client, api_key, "Work")

    resp = await client.get("/api/v1/me/stashes", headers=_auth(api_key))
    assert resp.status_code == 200
    stashes = resp.json()["stashes"]
    assert [s["name"] for s in stashes] == ["Work"]
    assert stashes[0]["scope_user_id"] == stash["scope_user_id"]


@pytest.mark.asyncio
async def test_stash_scope_user_cannot_log_in(client: AsyncClient, pool):
    api_key, _ = await _register(client)
    stash = await _create_stash(client, api_key)
    row = await pool.fetchrow(
        "SELECT password_hash FROM users WHERE id = $1",
        uuid.UUID(stash["scope_user_id"]),
    )
    assert row["password_hash"] is None


@pytest.mark.asyncio
async def test_stash_limit_fails_loud(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(stash_service, "MAX_STASHES", 2)
    api_key, _ = await _register(client)
    await _create_stash(client, api_key, "One")
    await _create_stash(client, api_key, "Two")
    resp = await client.post("/api/v1/me/stashes", json={"name": "Three"}, headers=_auth(api_key))
    assert resp.status_code == 409


# --- Isolation ---


@pytest.mark.asyncio
async def test_stash_content_is_isolated_from_personal(client: AsyncClient):
    api_key, _ = await _register(client)
    stash = await _create_stash(client, api_key)

    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "work-notes", "content": "quarterly plan"},
        headers=_scoped(api_key, stash["scope_user_id"]),
    )
    assert resp.status_code == 201, resp.text

    personal = await client.get("/api/v1/me/pages", headers=_auth(api_key))
    assert "work-notes" not in [p["name"] for p in personal.json()["pages"]]

    in_stash = await client.get(
        "/api/v1/me/pages", headers=_scoped(api_key, stash["scope_user_id"])
    )
    assert "work-notes" in [p["name"] for p in in_stash.json()["pages"]]


@pytest.mark.asyncio
async def test_two_stashes_are_isolated_from_each_other(client: AsyncClient):
    api_key, _ = await _register(client)
    work = await _create_stash(client, api_key, "Work")
    personal2 = await _create_stash(client, api_key, "Side project")

    await client.post(
        "/api/v1/me/pages/new",
        json={"name": "only-in-work", "content": "x"},
        headers=_scoped(api_key, work["scope_user_id"]),
    )
    other = await client.get(
        "/api/v1/me/pages", headers=_scoped(api_key, personal2["scope_user_id"])
    )
    assert "only-in-work" not in [p["name"] for p in other.json()["pages"]]


# --- Access control ---


@pytest.mark.asyncio
async def test_strangers_are_rejected_from_a_stash(client: AsyncClient):
    owner_key, _ = await _register(client)
    stash = await _create_stash(client, owner_key)
    stranger_key, _ = await _register(client)

    resp = await client.get(
        "/api/v1/me/pages", headers=_scoped(stranger_key, stash["scope_user_id"])
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_share_stash_content(client: AsyncClient):
    """The human owner keeps owner-only powers inside their stash — unlike a
    workspace member, who is deliberately locked out of sharing."""
    owner_key, _ = await _register(client)
    stash = await _create_stash(client, owner_key)
    recipient_email = f"{unique_name()}@example.com"
    recipient_key, _ = await _register_with_email(client, recipient_email)

    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "shared-from-stash", "content": "x"},
        headers=_scoped(owner_key, stash["scope_user_id"]),
    )
    resp = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page.json()["id"],
            "email": recipient_email,
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200, resp.text

    seen = await client.get(f"/api/v1/pages/{page.json()['id']}", headers=_auth(recipient_key))
    assert seen.status_code == 200


@pytest.mark.asyncio
async def test_rename_is_owner_only(client: AsyncClient):
    owner_key, _ = await _register(client)
    stash = await _create_stash(client, owner_key, "Work")
    stranger_key, _ = await _register(client)

    denied = await client.patch(
        f"/api/v1/me/stashes/{stash['id']}", json={"name": "Mine now"}, headers=_auth(stranger_key)
    )
    assert denied.status_code == 404

    renamed = await client.patch(
        f"/api/v1/me/stashes/{stash['id']}", json={"name": "Client work"}, headers=_auth(owner_key)
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Client work"


# --- Per-stash keys ---


@pytest.mark.asyncio
async def test_stash_key_acts_in_the_stash_without_a_header(client: AsyncClient, pool):
    owner_key, _ = await _register(client)
    stash = await _create_stash(client, owner_key)

    minted = await client.post(
        f"/api/v1/me/stashes/{stash['id']}/keys", json={"name": "agent"}, headers=_auth(owner_key)
    )
    assert minted.status_code == 201, minted.text
    stash_key = minted.json()["api_key"]

    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "agent-page", "content": "written by agent"},
        headers=_auth(stash_key),
    )
    assert resp.status_code == 201, resp.text
    owner = await pool.fetchval(
        "SELECT owner_user_id FROM pages WHERE id = $1", uuid.UUID(resp.json()["id"])
    )
    assert str(owner) == stash["scope_user_id"]


@pytest.mark.asyncio
async def test_stash_key_minting_is_owner_only(client: AsyncClient):
    owner_key, _ = await _register(client)
    stash = await _create_stash(client, owner_key)
    stranger_key, _ = await _register(client)

    resp = await client.post(
        f"/api/v1/me/stashes/{stash['id']}/keys", json={}, headers=_auth(stranger_key)
    )
    assert resp.status_code == 404
