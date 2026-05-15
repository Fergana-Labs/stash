"""Tests for Stash-mediated content access."""

import uuid

import pytest
from httpx import AsyncClient

from backend.models import StashItem
from backend.services import permission_service, stash_service

from .conftest import unique_name


async def _make_user(pool, name=None):
    name = name or unique_name()
    row = await pool.fetchrow(
        "INSERT INTO users (name) VALUES ($1) RETURNING id",
        name,
    )
    user_id = row["id"]
    await pool.execute(
        "INSERT INTO user_api_keys (user_id, key_hash, name) VALUES ($1, $2, 'test')",
        user_id,
        "hash_" + uuid.uuid4().hex,
    )
    return user_id


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name or unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _make_workspace(pool, creator_id):
    invite = uuid.uuid4().hex[:12]
    row = await pool.fetchrow(
        "INSERT INTO workspaces (name, creator_id, invite_code) VALUES ('ws', $1, $2) RETURNING id",
        creator_id,
        invite,
    )
    ws_id = row["id"]
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
        ws_id,
        creator_id,
    )
    return ws_id


async def _add_workspace_member(pool, workspace_id, user_id, role="editor"):
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, $3)",
        workspace_id,
        user_id,
        role,
    )


async def _make_folder(pool, workspace_id, created_by, name="folder", parent_folder_id=None):
    row = await pool.fetchrow(
        "INSERT INTO folders (workspace_id, parent_folder_id, name, created_by) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        workspace_id,
        parent_folder_id,
        name,
        created_by,
    )
    return row["id"]


async def _make_page(pool, workspace_id, created_by, folder_id=None, name="page"):
    row = await pool.fetchrow(
        "INSERT INTO pages (workspace_id, folder_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, $3, 'content', $4) RETURNING id",
        workspace_id,
        folder_id,
        name,
        created_by,
    )
    return row["id"]


async def _make_session(pool, workspace_id, created_by, session_id="session-1"):
    row = await pool.fetchrow(
        "INSERT INTO sessions (workspace_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, 'codex', $3) RETURNING id",
        workspace_id,
        session_id,
        created_by,
    )
    return row["id"]


async def _make_table(pool, workspace_id, created_by, name="table"):
    row = await pool.fetchrow(
        "INSERT INTO tables (workspace_id, name, created_by) VALUES ($1, $2, $3) RETURNING id",
        workspace_id,
        name,
        created_by,
    )
    return row["id"]


async def _make_history_event(pool, workspace_id, created_by):
    return await pool.fetchval(
        "INSERT INTO history_events (workspace_id, created_by, agent_name, event_type, content) "
        "VALUES ($1, $2, 'agent', 'message', 'hello') RETURNING id",
        workspace_id,
        created_by,
    )


async def _make_stash(workspace_id, owner_id, access, object_type, object_id):
    return await stash_service.create_stash(
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=f"{access} Stash",
        description="",
        access=access,
        discoverable=False,
        cover_image_url=None,
        items=[StashItem(object_type=object_type, object_id=object_id)],
    )


async def _add_stash_member(pool, stash_id, user_id, granted_by, permission="read"):
    await pool.execute(
        "INSERT INTO stash_members (stash_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, $3, $4)",
        stash_id,
        user_id,
        permission,
        granted_by,
    )


@pytest.mark.asyncio
async def test_owner_has_read_and_write_access(pool):
    user_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, user_id)
    folder_id = await _make_folder(pool, ws_id, user_id)

    assert await permission_service.check_access("folder", folder_id, user_id, workspace_id=ws_id)
    assert await permission_service.check_access(
        "folder", folder_id, user_id, workspace_id=ws_id, require_write=True
    )


@pytest.mark.asyncio
async def test_workspace_member_can_read_unstashed_content(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await _add_workspace_member(pool, ws_id, member_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)

    assert await permission_service.check_access("folder", folder_id, member_id, workspace_id=ws_id)


@pytest.mark.asyncio
async def test_workspace_member_cannot_write_unstashed_content(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await _add_workspace_member(pool, ws_id, member_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)

    result = await permission_service.check_access(
        "folder", folder_id, member_id, workspace_id=ws_id, require_write=True
    )

    assert not result


@pytest.mark.asyncio
async def test_non_member_cannot_read_unstashed_content(pool):
    owner_id = await _make_user(pool)
    stranger_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)

    assert not await permission_service.check_access(
        "folder", folder_id, stranger_id, workspace_id=ws_id
    )


@pytest.mark.asyncio
async def test_public_stash_makes_page_anonymously_readable(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id)

    await _make_stash(ws_id, owner_id, "public", "page", page_id)

    assert await permission_service.check_access("page", page_id, None)
    assert await permission_service.get_visibility("page", page_id) == "public"


@pytest.mark.asyncio
async def test_private_stash_hides_page_from_workspace_member(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await _add_workspace_member(pool, ws_id, member_id)
    page_id = await _make_page(pool, ws_id, owner_id)

    await _make_stash(ws_id, owner_id, "private", "page", page_id)

    assert await permission_service.check_access("page", page_id, owner_id, workspace_id=ws_id)
    assert not await permission_service.check_access("page", page_id, member_id, workspace_id=ws_id)
    assert await permission_service.get_visibility("page", page_id) == "private"


@pytest.mark.asyncio
async def test_private_stash_member_can_read_and_write_with_permission(pool):
    owner_id = await _make_user(pool)
    reader_id = await _make_user(pool)
    writer_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id)
    stash = await _make_stash(ws_id, owner_id, "private", "page", page_id)

    await _add_stash_member(pool, stash["id"], reader_id, owner_id, "read")
    await _add_stash_member(pool, stash["id"], writer_id, owner_id, "write")

    assert await permission_service.check_access("page", page_id, reader_id)
    assert not await permission_service.check_access("page", page_id, reader_id, require_write=True)
    assert await permission_service.check_access("page", page_id, writer_id, require_write=True)


@pytest.mark.asyncio
async def test_stash_member_api_grants_and_revokes_private_page_access(
    client: AsyncClient,
):
    owner_key, owner = await _register(client, "stash_owner")
    collaborator_key, collaborator = await _register(client, "stash_collaborator")

    workspace_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Member API workspace"},
        headers=_auth(owner_key),
    )
    assert workspace_resp.status_code == 201
    workspace = workspace_resp.json()

    page_resp = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={"name": "Private plan", "content": "# Private plan"},
        headers=_auth(owner_key),
    )
    assert page_resp.status_code == 201
    page = page_resp.json()

    stash_resp = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/stashes",
        json={
            "title": "Private plan stash",
            "access": "private",
            "items": [{"object_type": "page", "object_id": page["id"]}],
        },
        headers=_auth(owner_key),
    )
    assert stash_resp.status_code == 201
    stash = stash_resp.json()

    assert not await permission_service.check_access(
        "page",
        uuid.UUID(page["id"]),
        uuid.UUID(collaborator["id"]),
        require_write=True,
    )

    add_resp = await client.post(
        f"/api/v1/stashes/{stash['id']}/members",
        json={"user_id": collaborator["id"], "permission": "write"},
        headers=_auth(owner_key),
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["permission"] == "write"

    members_resp = await client.get(
        f"/api/v1/stashes/{stash['id']}/members",
        headers=_auth(owner_key),
    )
    assert members_resp.status_code == 200
    assert [member["user_id"] for member in members_resp.json()["members"]] == [
        collaborator["id"]
    ]
    assert await permission_service.check_access(
        "page",
        uuid.UUID(page["id"]),
        uuid.UUID(collaborator["id"]),
        require_write=True,
    )

    forbidden_resp = await client.post(
        f"/api/v1/stashes/{stash['id']}/members",
        json={"user_id": owner["id"], "permission": "read"},
        headers=_auth(collaborator_key),
    )
    assert forbidden_resp.status_code == 403

    delete_resp = await client.delete(
        f"/api/v1/stashes/{stash['id']}/members/{collaborator['id']}",
        headers=_auth(owner_key),
    )
    assert delete_resp.status_code == 204
    assert not await permission_service.check_access(
        "page",
        uuid.UUID(page["id"]),
        uuid.UUID(collaborator["id"]),
        require_write=True,
    )


@pytest.mark.asyncio
async def test_stash_write_member_can_create_shared_page_outside_workspace_files(
    client: AsyncClient,
):
    owner_key, _owner = await _register(client, "shared_page_owner")
    collaborator_key, collaborator = await _register(client, "shared_page_collaborator")

    workspace_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Shared Page workspace"},
        headers=_auth(owner_key),
    )
    assert workspace_resp.status_code == 201
    workspace = workspace_resp.json()

    page_resp = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={"name": "Source page", "content": "# Source page"},
        headers=_auth(owner_key),
    )
    assert page_resp.status_code == 201
    page = page_resp.json()

    stash_resp = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/stashes",
        json={
            "title": "Private edit stash",
            "access": "private",
            "items": [{"object_type": "page", "object_id": page["id"]}],
        },
        headers=_auth(owner_key),
    )
    assert stash_resp.status_code == 201
    stash = stash_resp.json()

    add_resp = await client.post(
        f"/api/v1/stashes/{stash['id']}/members",
        json={"user_id": collaborator["id"], "permission": "write"},
        headers=_auth(owner_key),
    )
    assert add_resp.status_code == 201

    shared_resp = await client.post(
        f"/api/v1/stashes/{stash['id']}/shared-pages",
        json={"name": "Collaborator note", "content": "# Collaborator note"},
        headers=_auth(collaborator_key),
    )
    assert shared_resp.status_code == 201
    shared_page = shared_resp.json()
    assert shared_page["metadata"]["shared_in_stash_id"] == stash["id"]

    stash_detail = await client.get(
        f"/api/v1/stashes/{stash['slug']}",
        headers=_auth(collaborator_key),
    )
    assert stash_detail.status_code == 200
    body = stash_detail.json()
    assert body["can_write"] is True
    assert [item["label"] for item in body["items"]] == [
        "Source page",
        "Collaborator note",
    ]

    pages_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/pages",
        headers=_auth(owner_key),
    )
    assert pages_resp.status_code == 200
    assert [item["name"] for item in pages_resp.json()["pages"]] == ["Source page"]

    tree_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/tree",
        headers=_auth(owner_key),
    )
    assert tree_resp.status_code == 200
    assert [item["name"] for item in tree_resp.json()["pages"]] == ["Source page"]


@pytest.mark.asyncio
async def test_private_stash_partitions_items_from_workspace_and_public_stashes(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id)

    await _make_stash(ws_id, owner_id, "private", "page", page_id)

    with pytest.raises(ValueError, match="private Stashes"):
        await _make_stash(ws_id, owner_id, "workspace", "page", page_id)


@pytest.mark.asyncio
async def test_folder_partition_blocks_descendant_page_conflicts(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=folder_id)

    await _make_stash(ws_id, owner_id, "private", "folder", folder_id)

    with pytest.raises(ValueError, match="private Stashes"):
        await _make_stash(ws_id, owner_id, "public", "page", page_id)


@pytest.mark.asyncio
async def test_page_partition_blocks_ancestor_folder_conflicts(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=folder_id)

    await _make_stash(ws_id, owner_id, "private", "page", page_id)

    with pytest.raises(ValueError, match="private Stashes"):
        await _make_stash(ws_id, owner_id, "workspace", "folder", folder_id)


@pytest.mark.asyncio
async def test_page_inherits_folder_stash_access(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await _add_workspace_member(pool, ws_id, member_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=folder_id)

    await _make_stash(ws_id, owner_id, "private", "folder", folder_id)

    assert not await permission_service.check_access("page", page_id, member_id, workspace_id=ws_id)


@pytest.mark.asyncio
async def test_nested_page_inherits_outer_folder_stash_access(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await _add_workspace_member(pool, ws_id, member_id)
    outer = await _make_folder(pool, ws_id, owner_id, name="outer")
    inner = await _make_folder(pool, ws_id, owner_id, name="inner", parent_folder_id=outer)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=inner)

    await _make_stash(ws_id, owner_id, "private", "folder", outer)

    assert not await permission_service.check_access("page", page_id, member_id)


@pytest.mark.asyncio
async def test_privacy_mutators_fail_fast(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id)

    with pytest.raises(ValueError, match="Stashes"):
        await permission_service.set_visibility("page", page_id, "private")

    with pytest.raises(ValueError, match="Stashes"):
        await permission_service.set_privacy_visibility("page", page_id, "private", owner_id)

    with pytest.raises(ValueError, match="Stash"):
        await permission_service.add_share("page", page_id, owner_id, "read", owner_id)


@pytest.mark.asyncio
async def test_resolve_workspace_for_content_types(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id)
    session_id = await _make_session(pool, ws_id, owner_id)
    table_id = await _make_table(pool, ws_id, owner_id)

    assert await permission_service.resolve_workspace_id("page", page_id) == ws_id
    assert await permission_service.resolve_workspace_id("session", session_id) == ws_id
    assert await permission_service.resolve_workspace_id("table", table_id) == ws_id
