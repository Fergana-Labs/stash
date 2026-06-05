"""Tests for workspace CRUD, invite codes, membership, and role enforcement."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    """Register a user. Returns (api_key, response_body)."""
    name = name or unique_name()
    resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": name,
            "password": "securepassword1",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# --- Creation ---


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient):
    key, _ = await _register(client)
    resp = await client.post(
        "/api/v1/workspaces",
        json={
            "name": "My Workspace",
            "description": "desc",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Workspace"
    assert body["invite_code"]
    assert body["member_count"] == 1


@pytest.mark.asyncio
async def test_create_workspace_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/workspaces", json={"name": "X"})
    assert resp.status_code == 401


# --- Listing ---


@pytest.mark.asyncio
async def test_list_my_workspaces(client: AsyncClient):
    key, _ = await _register(client)
    h = _auth(key)
    await client.post("/api/v1/workspaces", json={"name": "WS1"}, headers=h)
    await client.post("/api/v1/workspaces", json={"name": "WS2"}, headers=h)

    resp = await client.get("/api/v1/workspaces/mine", headers=h)
    assert resp.status_code == 200
    # Registration auto-provisions a default workspace, so WS1/WS2 come alongside it.
    names = {w["name"] for w in resp.json()["workspaces"]}
    assert {"WS1", "WS2"}.issubset(names)


@pytest.mark.asyncio
async def test_registration_auto_provisions_default_workspace(client: AsyncClient):
    key, body = await _register(client)
    resp = await client.get("/api/v1/workspaces/mine", headers=_auth(key))
    assert resp.status_code == 200
    workspaces = resp.json()["workspaces"]
    assert len(workspaces) == 1
    assert workspaces[0]["name"] == "Stash"
    assert workspaces[0]["member_count"] == 1


# --- Invite flow ---


@pytest.mark.asyncio
@pytest.mark.skip(reason="obsolete under single-owner model (C3): no workspace roles/multi-member")
async def test_join_by_invite_code(client: AsyncClient):
    owner_key, _ = await _register(client)
    joiner_key, _ = await _register(client)

    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()
    invite_code = ws["invite_code"]

    resp = await client.post(
        f"/api/v1/workspaces/join/{invite_code}",
        headers=_auth(joiner_key),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Team"

    members = (
        await client.get(
            f"/api/v1/workspaces/{ws['id']}/members",
            headers=_auth(joiner_key),
        )
    ).json()
    assert len(members) == 2


@pytest.mark.asyncio
async def test_invalid_invite_code_404(client: AsyncClient):
    key, _ = await _register(client)
    resp = await client.post("/api/v1/workspaces/join/badcode123", headers=_auth(key))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rotate_invite_code_owner(client: AsyncClient):
    owner_key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()
    old_code = ws["invite_code"]

    resp = await client.post(
        f"/api/v1/workspaces/{ws['id']}/invite-code/rotate",
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200
    new_code = resp.json()["invite_code"]
    assert new_code and new_code != old_code

    # Old code no longer works
    other_key, _ = await _register(client)
    bad = await client.post(f"/api/v1/workspaces/join/{old_code}", headers=_auth(other_key))
    assert bad.status_code == 404

    # New code works
    good = await client.post(f"/api/v1/workspaces/join/{new_code}", headers=_auth(other_key))
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_rotate_invite_code_member_forbidden(client: AsyncClient):
    owner_key, _ = await _register(client)
    member_key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()
    await client.post(f"/api/v1/workspaces/join/{ws['invite_code']}", headers=_auth(member_key))

    resp = await client.post(
        f"/api/v1/workspaces/{ws['id']}/invite-code/rotate",
        headers=_auth(member_key),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.skip(reason="obsolete under single-owner model (C3): no workspace roles/multi-member")
async def test_magic_invite_redeem_assigns_editor_role(client: AsyncClient):
    owner_key, _ = await _register(client)
    joiner_key, joiner = await _register(client)
    ws = (
        await client.post(
            "/api/v1/workspaces", json={"name": "Magic Team"}, headers=_auth(owner_key)
        )
    ).json()

    invite = await client.post(
        f"/api/v1/workspaces/{ws['id']}/invite-tokens",
        json={"max_uses": 1, "ttl_days": 7},
        headers=_auth(owner_key),
    )
    assert invite.status_code == 201

    redeemed = await client.post(
        "/api/v1/workspaces/redeem-invite",
        json={"token": invite.json()["token"]},
        headers=_auth(joiner_key),
    )
    assert redeemed.status_code == 200

    members = (
        await client.get(
            f"/api/v1/workspaces/{ws['id']}/members",
            headers=_auth(owner_key),
        )
    ).json()
    roles = {member["user_id"]: member["role"] for member in members}
    assert roles[joiner["id"]] == "editor"


# --- Update / Delete ---


@pytest.mark.asyncio
async def test_update_workspace(client: AsyncClient):
    key, _ = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Old"}, headers=_auth(key))).json()

    resp = await client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"name": "New"},
        headers=_auth(key),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.asyncio
@pytest.mark.skip(reason="obsolete under single-owner model (C3): no workspace roles/multi-member")
async def test_viewer_cannot_update_workspace(client: AsyncClient):
    owner_key, _ = await _register(client)
    member_key, member_body = await _register(client)
    member_id = member_body["id"]

    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()
    await client.post(f"/api/v1/workspaces/join/{ws['invite_code']}", headers=_auth(member_key))

    # Editors (the default for joiners) can update; demote to viewer to verify
    # read-only access.
    demote = await client.patch(
        f"/api/v1/workspaces/{ws['id']}/members/{member_id}",
        json={"role": "viewer"},
        headers=_auth(owner_key),
    )
    assert demote.status_code == 200

    resp = await client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"name": "Hacked"},
        headers=_auth(member_key),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_editor_can_update_workspace(client: AsyncClient):
    owner_key, _ = await _register(client)
    member_key, _ = await _register(client)

    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()
    await client.post(f"/api/v1/workspaces/join/{ws['invite_code']}", headers=_auth(member_key))

    # Default role for joiners is editor; editors can rename/describe the stash.
    resp = await client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"name": "Edited by member"},
        headers=_auth(member_key),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Edited by member"


@pytest.mark.asyncio
async def test_delete_workspace(client: AsyncClient):
    key, _ = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Temp"}, headers=_auth(key))).json()

    resp = await client.delete(f"/api/v1/workspaces/{ws['id']}", headers=_auth(key))
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/workspaces/{ws['id']}", headers=_auth(key))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_owner_cannot_delete_workspace(client: AsyncClient):
    owner_key, _ = await _register(client)
    member_key, _ = await _register(client)

    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()
    await client.post(f"/api/v1/workspaces/join/{ws['invite_code']}", headers=_auth(member_key))

    resp = await client.delete(f"/api/v1/workspaces/{ws['id']}", headers=_auth(member_key))
    assert resp.status_code == 403


# --- Leave ---


@pytest.mark.asyncio
async def test_member_can_leave(client: AsyncClient):
    owner_key, _ = await _register(client)
    member_key, _ = await _register(client)

    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Team"}, headers=_auth(owner_key))
    ).json()
    await client.post(f"/api/v1/workspaces/join/{ws['invite_code']}", headers=_auth(member_key))

    resp = await client.post(f"/api/v1/workspaces/{ws['id']}/leave", headers=_auth(member_key))
    assert resp.status_code == 204

    members = (
        await client.get(
            f"/api/v1/workspaces/{ws['id']}/members",
            headers=_auth(owner_key),
        )
    ).json()
    assert len(members) == 1


@pytest.mark.asyncio
async def test_owner_cannot_leave(client: AsyncClient):
    key, _ = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Mine"}, headers=_auth(key))).json()

    resp = await client.post(f"/api/v1/workspaces/{ws['id']}/leave", headers=_auth(key))
    assert resp.status_code == 400
