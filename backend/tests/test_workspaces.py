"""Tests for workspace CRUD, invite codes, membership, and role enforcement."""

from uuid import UUID

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


@pytest.mark.asyncio
async def test_get_workspace_does_not_auto_join_non_member(client: AsyncClient, pool):
    owner_key, _ = await _register(client)
    stranger_key, stranger = await _register(client)
    workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Private Team"},
            headers=_auth(owner_key),
        )
    ).json()

    response = await client.get(
        f"/api/v1/workspaces/{workspace['id']}",
        headers=_auth(stranger_key),
    )

    assert response.status_code == 404
    assert not await pool.fetchval(
        "SELECT 1 FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        UUID(workspace["id"]),
        UUID(stranger["id"]),
    )


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
async def test_managed_auth_disables_legacy_invite_codes(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    from backend.config import settings
    from backend.managed.auth0 import jwt as auth0_jwt
    from backend.managed.auth0.users import get_or_create_user_row_from_auth0

    await pool.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth0_sub VARCHAR(128) UNIQUE")
    token_to_sub = {
        "owner-auth0-token": f"google-oauth2|{unique_name('managed_owner')}",
        "joiner-auth0-token": f"google-oauth2|{unique_name('managed_joiner')}",
    }

    async def fake_validate_auth0_token(token: str) -> dict:
        return {"sub": token_to_sub[token]}

    await get_or_create_user_row_from_auth0(
        auth0_sub=token_to_sub["owner-auth0-token"],
        email="owner@example.com",
        name="Managed Owner",
    )
    await get_or_create_user_row_from_auth0(
        auth0_sub=token_to_sub["joiner-auth0-token"],
        email="joiner@example.com",
        name="Managed Joiner",
    )
    monkeypatch.setattr(settings, "AUTH0_ENABLED", True)
    monkeypatch.setattr(auth0_jwt, "validate_auth0_token", fake_validate_auth0_token)
    owner_headers = {"Authorization": "Bearer owner-auth0-token"}
    joiner_headers = {"Authorization": "Bearer joiner-auth0-token"}

    created = await client.post(
        "/api/v1/workspaces",
        json={"name": "Managed Team"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    workspace = created.json()
    assert workspace["invite_code"] == ""

    legacy_invite_code = await pool.fetchval(
        "SELECT invite_code FROM workspaces WHERE id = $1",
        UUID(workspace["id"]),
    )
    assert legacy_invite_code

    listed = await client.get("/api/v1/workspaces/mine", headers=owner_headers)
    assert listed.status_code == 200
    assert all(w["invite_code"] == "" for w in listed.json()["workspaces"])

    fetched = await client.get(
        f"/api/v1/workspaces/{workspace['id']}",
        headers=owner_headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["invite_code"] == ""

    legacy_join = await client.post(
        f"/api/v1/workspaces/join/{legacy_invite_code}",
        headers=joiner_headers,
    )
    assert legacy_join.status_code == 404

    rotate = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/invite-code/rotate",
        headers=owner_headers,
    )
    assert rotate.status_code == 404

    invite = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/invite-tokens",
        json={"max_uses": 1, "ttl_days": 7},
        headers=owner_headers,
    )
    assert invite.status_code == 201

    redeemed = await client.post(
        "/api/v1/workspaces/redeem-invite",
        json={"token": invite.json()["token"]},
        headers=joiner_headers,
    )
    assert redeemed.status_code == 200
    assert redeemed.json()["invite_code"] == ""


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

    # Default role for joiners is editor; editors can rename/describe the skill.
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
async def test_delete_workspace_deletes_stored_files_and_session_artifacts(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    key, user = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Temp"}, headers=_auth(key))).json()
    workspace_id = UUID(ws["id"])
    user_id = UUID(user["id"])

    await pool.execute(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        workspace_id,
        "plans.pdf",
        "application/pdf",
        12,
        "file-key",
        user_id,
    )
    session_row_id = await pool.fetchval(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id",
        workspace_id,
        "sess-workspace-delete",
        "codex",
        user_id,
    )
    await pool.execute(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, $4)",
        session_row_id,
        "artifact.txt",
        "artifact-key",
        42,
    )

    deleted_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        # Blobs are purged only after the DB delete commits — a failed delete
        # must never leave live rows pointing at destroyed storage objects.
        assert (
            await pool.fetchval("SELECT COUNT(*) FROM workspaces WHERE id = $1", workspace_id) == 0
        )
        deleted_keys.append(storage_key)

    monkeypatch.setattr("backend.routers.workspaces.storage_service.delete_file", fake_delete_file)

    resp = await client.delete(f"/api/v1/workspaces/{ws['id']}", headers=_auth(key))
    assert resp.status_code == 204
    assert deleted_keys == ["artifact-key", "file-key"]
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM files WHERE workspace_id = $1", workspace_id) == 0
    )
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM sessions WHERE workspace_id = $1", workspace_id)
        == 0
    )


@pytest.mark.asyncio
async def test_delete_workspace_keeps_storage_keys_referenced_by_other_workspaces(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    key, user = await _register(client)
    first = (
        await client.post("/api/v1/workspaces", json={"name": "First"}, headers=_auth(key))
    ).json()
    second = (
        await client.post("/api/v1/workspaces", json={"name": "Second"}, headers=_auth(key))
    ).json()
    first_workspace_id = UUID(first["id"])
    second_workspace_id = UUID(second["id"])
    user_id = UUID(user["id"])

    for workspace_id, name, storage_key in [
        (first_workspace_id, "first-plan.pdf", "shared-file-key"),
        (first_workspace_id, "first-private.pdf", "first-private-file-key"),
        (second_workspace_id, "second-plan.pdf", "shared-file-key"),
    ]:
        await pool.execute(
            "INSERT INTO files "
            "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            workspace_id,
            name,
            "application/pdf",
            12,
            storage_key,
            user_id,
        )

    first_session_id = await pool.fetchval(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id",
        first_workspace_id,
        "first-session",
        "codex",
        user_id,
    )
    second_session_id = await pool.fetchval(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id",
        second_workspace_id,
        "second-session",
        "codex",
        user_id,
    )
    for session_id, file_path, storage_key in [
        (first_session_id, "private.txt", "first-private-artifact-key"),
        (first_session_id, "shared.txt", "shared-artifact-key"),
        (second_session_id, "shared.txt", "shared-artifact-key"),
    ]:
        await pool.execute(
            "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
            "VALUES ($1, $2, $3, $4)",
            session_id,
            file_path,
            storage_key,
            42,
        )

    deleted_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        deleted_keys.append(storage_key)

    monkeypatch.setattr("backend.routers.workspaces.storage_service.delete_file", fake_delete_file)

    resp = await client.delete(f"/api/v1/workspaces/{first['id']}", headers=_auth(key))

    assert resp.status_code == 204
    assert deleted_keys == ["first-private-artifact-key", "first-private-file-key"]
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM files WHERE workspace_id = $1",
            first_workspace_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM files WHERE workspace_id = $1",
            second_workspace_id,
        )
        == 1
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
            second_session_id,
        )
        == 1
    )


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
async def test_member_leave_removes_workspace_shares_and_stash_access(
    client: AsyncClient,
    pool,
):
    """Shares confer access independently of membership, so leaving must
    revoke the shares the member received and the ones they granted."""
    owner_key, _owner = await _register(client, "offboarding_owner")
    member_name = unique_name("offboarding_member")
    member_email = f"{member_name}@example.com"
    member_resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": member_name,
            "email": member_email,
            "password": "securepassword1",
        },
    )
    assert member_resp.status_code == 201
    member_key = member_resp.json()["api_key"]
    member_id = UUID(member_resp.json()["id"])
    _recipient_key, recipient = await _register(client, "offboarding_recipient")
    recipient_id = UUID(recipient["id"])

    ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Offboarding Team"},
            headers=_auth(owner_key),
        )
    ).json()
    workspace_id = UUID(ws["id"])
    joined = await client.post(
        f"/api/v1/workspaces/join/{ws['invite_code']}",
        headers=_auth(member_key),
    )
    assert joined.status_code == 200

    page = (
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/pages/new",
            json={"name": "Confidential", "content": "Webflow confidential plan"},
            headers=_auth(owner_key),
        )
    ).json()
    page_id = page["id"]
    shared = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": member_email,
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert shared.status_code == 200
    await pool.execute(
        "INSERT INTO shares "
        "(workspace_id, object_type, object_id, principal_type, principal_id, permission, created_by) "
        "VALUES ($1, 'page', $2, 'user', $3, 'read', $4)",
        workspace_id,
        UUID(page_id),
        recipient_id,
        member_id,
    )
    await pool.execute(
        "INSERT INTO share_invites "
        "(workspace_id, object_type, object_id, email, permission, created_by) "
        "VALUES ($1, 'page', $2, $3, 'read', $4)",
        workspace_id,
        UUID(page_id),
        "future-webflow-user@example.com",
        member_id,
    )

    left = await client.post(
        f"/api/v1/workspaces/{ws['id']}/leave",
        headers=_auth(member_key),
    )

    assert left.status_code == 204
    # The share the member received must not outlive their membership.
    assert (
        await client.get(
            f"/api/v1/workspaces/{ws['id']}/pages/{page_id}",
            headers=_auth(member_key),
        )
    ).status_code == 404
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM shares "
            "WHERE workspace_id = $1 AND principal_type = 'user' AND principal_id = $2",
            workspace_id,
            member_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM shares WHERE workspace_id = $1 AND created_by = $2",
            workspace_id,
            member_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM share_invites WHERE workspace_id = $1 AND created_by = $2",
            workspace_id,
            member_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_owner_can_remove_member_and_revoke_access(client: AsyncClient, pool):
    """Removal must offboard like a voluntary leave: shares confer access
    independently of membership, so kicking a member has to revoke them too,
    not just drop the membership row."""
    owner_key, owner = await _register(client, "kick_owner")
    member_key, member = await _register(client, "kick_member")
    member_id = UUID(member["id"])

    ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Kick Team"},
            headers=_auth(owner_key),
        )
    ).json()
    workspace_id = UUID(ws["id"])
    joined = await client.post(
        f"/api/v1/workspaces/join/{ws['invite_code']}",
        headers=_auth(member_key),
    )
    assert joined.status_code == 200

    page = (
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/pages/new",
            json={"name": "Confidential", "content": "Kick offboarding plan"},
            headers=_auth(owner_key),
        )
    ).json()
    await pool.execute(
        "INSERT INTO shares "
        "(workspace_id, object_type, object_id, principal_type, principal_id, permission, created_by) "
        "VALUES ($1, 'page', $2, 'user', $3, 'read', $4)",
        workspace_id,
        UUID(page["id"]),
        member_id,
        UUID(owner["id"]),
    )

    # Members cannot kick — owner-only.
    forbidden = await client.delete(
        f"/api/v1/workspaces/{ws['id']}/members/{owner['id']}",
        headers=_auth(member_key),
    )
    assert forbidden.status_code == 403

    removed = await client.delete(
        f"/api/v1/workspaces/{ws['id']}/members/{member_id}",
        headers=_auth(owner_key),
    )
    assert removed.status_code == 204

    assert (
        await client.get(
            f"/api/v1/workspaces/{ws['id']}/pages/{page['id']}",
            headers=_auth(member_key),
        )
    ).status_code == 404
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM shares "
            "WHERE workspace_id = $1 AND principal_type = 'user' AND principal_id = $2",
            workspace_id,
            member_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
            workspace_id,
            member_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_owner_cannot_leave(client: AsyncClient):
    key, _ = await _register(client)
    ws = (await client.post("/api/v1/workspaces", json={"name": "Mine"}, headers=_auth(key))).json()

    resp = await client.post(f"/api/v1/workspaces/{ws['id']}/leave", headers=_auth(key))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_new_page_button_never_collides(client: AsyncClient):
    """The 'New page' button always sends 'Untitled'. Clicking it repeatedly must
    keep working: each new page gets the next free name instead of a 409."""
    key, _ = await _register(client)
    ws = (
        await client.post("/api/v1/workspaces", json={"name": "Pages"}, headers=_auth(key))
    ).json()

    names = []
    for _ in range(3):
        resp = await client.post(
            f"/api/v1/workspaces/{ws['id']}/pages/new",
            json={"name": "Untitled"},
            headers=_auth(key),
        )
        assert resp.status_code == 201
        names.append(resp.json()["name"])

    assert names == ["Untitled", "Untitled (2)", "Untitled (3)"]
