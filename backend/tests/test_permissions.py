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
        "INSERT INTO users (name, display_name) VALUES ($1, $2) RETURNING id",
        name,
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


async def _make_file(pool, workspace_id, uploaded_by, folder_id=None, name="file.txt"):
    row = await pool.fetchrow(
        "INSERT INTO files "
        "(workspace_id, folder_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, 'text/plain', 12, $4, $5) RETURNING id",
        workspace_id,
        folder_id,
        name,
        f"test/{uuid.uuid4().hex}.txt",
        uploaded_by,
    )
    return row["id"]


async def _make_history_event(
    pool,
    workspace_id,
    created_by,
    session_id=None,
    content="hello",
    event_type="message",
):
    return await pool.fetchval(
        "INSERT INTO history_events "
        "(workspace_id, created_by, agent_name, event_type, content, session_id) "
        "VALUES ($1, $2, 'agent', $3, $4, $5) RETURNING id",
        workspace_id,
        created_by,
        event_type,
        content,
        session_id,
    )


async def _make_stash(workspace_id, owner_id, access, object_type, object_id):
    workspace_permission, public_permission = _permissions_for_access(access)
    return await stash_service.create_stash(
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=f"{access} Stash",
        description="",
        workspace_permission=workspace_permission,
        public_permission=public_permission,
        discoverable=False,
        cover_image_url=None,
        items=[StashItem(object_type=object_type, object_id=object_id)],
    )


def _permissions_for_access(access):
    if access == "private":
        return "none", "none"
    if access == "public":
        return "read", "read"
    return "read", "none"


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
async def test_workspace_editor_can_write_unstashed_content(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await _add_workspace_member(pool, ws_id, member_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)

    result = await permission_service.check_access(
        "folder", folder_id, member_id, workspace_id=ws_id, require_write=True
    )

    assert result


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
async def test_private_stash_hides_member_content_from_workspace_admin(client: AsyncClient):
    admin_key, admin = await _register(client, "private_stash_admin")
    member_key, _member = await _register(client, "private_stash_member_owner")

    workspace_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Admin privacy workspace"},
        headers=_auth(admin_key),
    )
    assert workspace_resp.status_code == 201
    workspace = workspace_resp.json()

    join_resp = await client.post(
        f"/api/v1/workspaces/join/{workspace['invite_code']}",
        headers=_auth(member_key),
    )
    assert join_resp.status_code == 200

    page_resp = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/pages/new",
        json={"name": "Member private page", "content": "private to member"},
        headers=_auth(member_key),
    )
    assert page_resp.status_code == 201
    page = page_resp.json()

    stash_resp = await client.post(
        f"/api/v1/workspaces/{workspace['id']}/stashes",
        json={
            "title": "Member private stash",
            "workspace_permission": "none",
            "public_permission": "none",
            "items": [{"object_type": "page", "object_id": page["id"]}],
        },
        headers=_auth(member_key),
    )
    assert stash_resp.status_code == 201
    stash = stash_resp.json()

    assert not await permission_service.check_access(
        "page",
        uuid.UUID(page["id"]),
        uuid.UUID(admin["id"]),
        workspace_id=uuid.UUID(workspace["id"]),
    )
    assert not await stash_service.user_can_read(
        uuid.UUID(stash["id"]),
        uuid.UUID(admin["id"]),
    )

    page_get_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/pages/{page['id']}",
        headers=_auth(admin_key),
    )
    assert page_get_resp.status_code == 404

    stashes_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/stashes",
        headers=_auth(admin_key),
    )
    assert stashes_resp.status_code == 200
    assert stashes_resp.json()["stashes"] == []


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
async def test_workspace_stash_content_requires_stash_write_permission(client: AsyncClient):
    owner_key, _owner = await _register(client, "workspace_stash_owner")
    member_key, member = await _register(client, "workspace_stash_member")

    workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Workspace stash permissions"},
            headers=_auth(owner_key),
        )
    ).json()
    join_resp = await client.post(
        f"/api/v1/workspaces/join/{workspace['invite_code']}",
        headers=_auth(member_key),
    )
    assert join_resp.status_code == 200

    page = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/pages/new",
            json={"name": "Shared plan", "content": "original"},
            headers=_auth(owner_key),
        )
    ).json()
    stash = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/stashes",
            json={
                "title": "Workspace plan",
                "workspace_permission": "read",
                "public_permission": "none",
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(owner_key),
        )
    ).json()

    denied = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/pages/{page['id']}",
        json={"content": "member edit"},
        headers=_auth(member_key),
    )
    assert denied.status_code == 404

    grant = await client.post(
        f"/api/v1/stashes/{stash['id']}/members",
        json={"user_id": member["id"], "permission": "write"},
        headers=_auth(owner_key),
    )
    assert grant.status_code == 201

    allowed = await client.patch(
        f"/api/v1/workspaces/{workspace['id']}/pages/{page['id']}",
        json={"content": "member edit"},
        headers=_auth(member_key),
    )
    assert allowed.status_code == 200
    assert allowed.json()["content_markdown"] == "member edit"


@pytest.mark.asyncio
async def test_public_view_with_workspace_edit_permissions(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    stranger_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await _add_workspace_member(pool, ws_id, member_id)
    page_id = await _make_page(pool, ws_id, owner_id)

    await stash_service.create_stash(
        workspace_id=ws_id,
        owner_id=owner_id,
        title="Public read workspace edit",
        description="",
        workspace_permission="write",
        public_permission="read",
        discoverable=False,
        cover_image_url=None,
        items=[StashItem(object_type="page", object_id=page_id)],
    )

    assert await permission_service.check_access("page", page_id, None)
    assert await permission_service.check_access("page", page_id, member_id, require_write=True)
    assert not await permission_service.check_access(
        "page",
        page_id,
        stranger_id,
        require_write=True,
    )


@pytest.mark.asyncio
async def test_public_edit_permission_allows_authenticated_writer(pool):
    owner_id = await _make_user(pool)
    stranger_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id)

    await stash_service.create_stash(
        workspace_id=ws_id,
        owner_id=owner_id,
        title="Public edit",
        description="",
        workspace_permission="read",
        public_permission="write",
        discoverable=False,
        cover_image_url=None,
        items=[StashItem(object_type="page", object_id=page_id)],
    )

    assert await permission_service.check_access("page", page_id, None)
    assert await permission_service.check_access("page", page_id, stranger_id, require_write=True)


@pytest.mark.asyncio
async def test_invited_private_external_stash_can_be_added_to_workspace(client: AsyncClient):
    owner_key, _owner = await _register(client, "private_external_owner")
    collaborator_key, collaborator = await _register(client, "private_external_collaborator")

    source_workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Source workspace"},
            headers=_auth(owner_key),
        )
    ).json()
    target_workspace = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Target workspace"},
            headers=_auth(collaborator_key),
        )
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{source_workspace['id']}/pages/new",
            json={"name": "Private brief", "content": "private"},
            headers=_auth(owner_key),
        )
    ).json()
    stash = (
        await client.post(
            f"/api/v1/workspaces/{source_workspace['id']}/stashes",
            json={
                "title": "Private external brief",
                "workspace_permission": "none",
                "public_permission": "none",
                "items": [{"object_type": "page", "object_id": page["id"]}],
            },
            headers=_auth(owner_key),
        )
    ).json()
    grant = await client.post(
        f"/api/v1/stashes/{stash['id']}/members",
        json={"user_id": collaborator["id"], "permission": "read"},
        headers=_auth(owner_key),
    )
    assert grant.status_code == 201

    added = await client.post(
        f"/api/v1/stashes/{stash['slug']}/add-to-workspace",
        json={"workspace_id": target_workspace["id"]},
        headers=_auth(collaborator_key),
    )
    assert added.status_code == 201
    fork = added.json()
    assert fork["is_external"] is True
    assert fork["workspace_id"] == target_workspace["id"]
    assert fork["added_to_workspace_id"] == target_workspace["id"]
    assert fork["forked_from_stash_id"] == stash["id"]
    assert fork["id"] != stash["id"]

    fork_page_id = fork["items"][0]["object_id"]
    fork_page = await client.get(
        f"/api/v1/workspaces/{target_workspace['id']}/pages/{fork_page_id}",
        headers=_auth(collaborator_key),
    )
    assert fork_page.status_code == 200
    assert fork_page.json()["content_markdown"] == "private"

    update_source = await client.patch(
        f"/api/v1/workspaces/{source_workspace['id']}/pages/{page['id']}",
        json={"content": "updated source"},
        headers=_auth(owner_key),
    )
    assert update_source.status_code == 200

    fork_page_after_source_edit = await client.get(
        f"/api/v1/workspaces/{target_workspace['id']}/pages/{fork_page_id}",
        headers=_auth(collaborator_key),
    )
    assert fork_page_after_source_edit.status_code == 200
    assert fork_page_after_source_edit.json()["content_markdown"] == "private"


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
            "workspace_permission": "none",
            "public_permission": "none",
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
    assert [member["user_id"] for member in members_resp.json()["members"]] == [collaborator["id"]]
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
            "workspace_permission": "none",
            "public_permission": "none",
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
async def test_private_stash_hides_session_surfaces_until_user_is_added(
    client: AsyncClient,
    pool,
):
    owner_key, owner = await _register(client, "session_privacy_owner")
    member_key, member = await _register(client, "session_privacy_member")

    workspace_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Session Privacy workspace"},
        headers=_auth(owner_key),
    )
    assert workspace_resp.status_code == 201
    workspace = workspace_resp.json()
    workspace_id = uuid.UUID(workspace["id"])
    owner_id = uuid.UUID(owner["id"])
    member_id = uuid.UUID(member["id"])

    await _add_workspace_member(pool, workspace_id, member_id)
    session_row_id = await _make_session(
        pool,
        workspace_id,
        owner_id,
        session_id="private-session-1",
    )
    await _make_history_event(
        pool,
        workspace_id,
        owner_id,
        session_id="private-session-1",
        content="secret session note",
        event_type="user_message",
    )
    stash = await _make_stash(
        workspace_id,
        owner_id,
        "private",
        "session",
        session_row_id,
    )

    overview_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/overview",
        headers=_auth(member_key),
    )
    assert overview_resp.status_code == 200
    assert overview_resp.json()["sessions"] == []

    sidebar_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/sidebar",
        headers=_auth(member_key),
    )
    assert sidebar_resp.status_code == 200
    assert sidebar_resp.json()["sessions"] == []

    transcript_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/transcripts/private-session-1",
        headers=_auth(member_key),
    )
    assert transcript_resp.status_code == 404

    query_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/sessions/events",
        params={"session_id": "private-session-1"},
        headers=_auth(member_key),
    )
    assert query_resp.status_code == 200
    assert query_resp.json()["events"] == []

    search_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/sessions/events/search",
        params={"q": "secret"},
        headers=_auth(member_key),
    )
    assert search_resp.status_code == 200
    assert search_resp.json()["events"] == []

    my_sessions_resp = await client.get(
        "/api/v1/me/sessions",
        params={"workspace_id": workspace["id"]},
        headers=_auth(member_key),
    )
    assert my_sessions_resp.status_code == 200
    assert my_sessions_resp.json()["sessions"] == []

    all_events_resp = await client.get(
        "/api/v1/me/session-events",
        headers=_auth(member_key),
    )
    assert all_events_resp.status_code == 200
    assert all_events_resp.json()["events"] == []

    activity_resp = await client.get(
        "/api/v1/me/activity",
        params={"workspace_id": workspace["id"]},
        headers=_auth(member_key),
    )
    assert activity_resp.status_code == 200
    assert "session.uploaded" not in [event["kind"] for event in activity_resp.json()]

    timeline_resp = await client.get(
        "/api/v1/me/activity-timeline",
        params={"workspace_id": workspace["id"]},
        headers=_auth(member_key),
    )
    assert timeline_resp.status_code == 200
    assert timeline_resp.json()["contributors"] == []

    await _add_stash_member(pool, stash["id"], member_id, owner_id, "read")

    overview_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/overview",
        headers=_auth(member_key),
    )
    assert overview_resp.status_code == 200
    assert [session["session_id"] for session in overview_resp.json()["sessions"]] == [
        "private-session-1"
    ]

    transcript_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/transcripts/private-session-1",
        headers=_auth(member_key),
    )
    assert transcript_resp.status_code == 200
    assert transcript_resp.json()["event_count"] == 1

    search_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/sessions/events/search",
        params={"q": "secret"},
        headers=_auth(member_key),
    )
    assert search_resp.status_code == 200
    assert [event["session_id"] for event in search_resp.json()["events"]] == ["private-session-1"]

    activity_resp = await client.get(
        "/api/v1/me/activity",
        params={"workspace_id": workspace["id"]},
        headers=_auth(member_key),
    )
    assert activity_resp.status_code == 200
    assert "session.uploaded" in [event["kind"] for event in activity_resp.json()]

    timeline_resp = await client.get(
        "/api/v1/me/activity-timeline",
        params={"workspace_id": workspace["id"]},
        headers=_auth(member_key),
    )
    assert timeline_resp.status_code == 200
    assert timeline_resp.json()["contributors"] == ["session_privacy_owner / agent"]


@pytest.mark.asyncio
async def test_private_stash_hides_files_pages_and_tables_until_user_is_added(
    client: AsyncClient,
    pool,
):
    owner_key, owner = await _register(client, "content_privacy_owner")
    member_key, member = await _register(client, "content_privacy_member")

    workspace_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Content Privacy workspace"},
        headers=_auth(owner_key),
    )
    assert workspace_resp.status_code == 201
    workspace = workspace_resp.json()
    workspace_id = uuid.UUID(workspace["id"])
    owner_id = uuid.UUID(owner["id"])
    member_id = uuid.UUID(member["id"])
    await _add_workspace_member(pool, workspace_id, member_id)

    page_id = await _make_page(pool, workspace_id, owner_id, name="Private page")
    file_id = await _make_file(pool, workspace_id, owner_id, name="private.txt")
    table_id = await _make_table(pool, workspace_id, owner_id, name="Private table")

    page_stash = await _make_stash(workspace_id, owner_id, "private", "page", page_id)
    file_stash = await _make_stash(workspace_id, owner_id, "private", "file", file_id)
    table_stash = await _make_stash(workspace_id, owner_id, "private", "table", table_id)

    overview_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/overview",
        headers=_auth(member_key),
    )
    assert overview_resp.status_code == 200
    files_payload = overview_resp.json()["files"]
    assert files_payload["pages"] == []
    assert files_payload["files"] == []

    pages_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/pages",
        headers=_auth(member_key),
    )
    assert pages_resp.status_code == 200
    assert pages_resp.json()["pages"] == []

    page_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/pages/{page_id}",
        headers=_auth(member_key),
    )
    assert page_resp.status_code == 404

    tables_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/tables",
        headers=_auth(member_key),
    )
    assert tables_resp.status_code == 200
    assert tables_resp.json()["tables"] == []

    table_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/tables/{table_id}",
        headers=_auth(member_key),
    )
    assert table_resp.status_code == 404

    await _add_stash_member(pool, page_stash["id"], member_id, owner_id, "read")
    await _add_stash_member(pool, file_stash["id"], member_id, owner_id, "read")
    await _add_stash_member(pool, table_stash["id"], member_id, owner_id, "read")

    overview_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/overview",
        headers=_auth(member_key),
    )
    assert overview_resp.status_code == 200
    files_payload = overview_resp.json()["files"]
    assert [page["name"] for page in files_payload["pages"]] == ["Private page"]
    assert [file["name"] for file in files_payload["files"]] == ["private.txt"]

    tables_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/tables",
        headers=_auth(member_key),
    )
    assert tables_resp.status_code == 200
    assert [table["name"] for table in tables_resp.json()["tables"]] == ["Private table"]


@pytest.mark.asyncio
async def test_folder_contents_do_not_leak_private_child_counts(client: AsyncClient, pool):
    owner_key, owner = await _register(client, "folder_count_owner")
    member_key, member = await _register(client, "folder_count_member")

    workspace_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Folder Count Privacy workspace"},
        headers=_auth(owner_key),
    )
    assert workspace_resp.status_code == 201
    workspace = workspace_resp.json()
    workspace_id = uuid.UUID(workspace["id"])
    owner_id = uuid.UUID(owner["id"])
    member_id = uuid.UUID(member["id"])
    await _add_workspace_member(pool, workspace_id, member_id)

    parent_id = await _make_folder(pool, workspace_id, owner_id, name="Parent")
    child_id = await _make_folder(
        pool,
        workspace_id,
        owner_id,
        name="Child",
        parent_folder_id=parent_id,
    )
    page_id = await _make_page(pool, workspace_id, owner_id, folder_id=child_id)
    file_id = await _make_file(pool, workspace_id, owner_id, folder_id=child_id)

    await _make_stash(workspace_id, owner_id, "private", "page", page_id)
    await _make_stash(workspace_id, owner_id, "private", "file", file_id)

    contents_resp = await client.get(
        f"/api/v1/workspaces/{workspace['id']}/folders/{parent_id}/contents",
        headers=_auth(member_key),
    )
    assert contents_resp.status_code == 200
    child = contents_resp.json()["subfolders"][0]
    assert child["name"] == "Child"
    assert child["page_count"] == 0
    assert child["file_count"] == 0


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
async def test_page_reports_stash_membership_from_parent_folder(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=folder_id)
    stash = await _make_stash(ws_id, owner_id, "workspace", "folder", folder_id)

    stashes = await stash_service.list_object_stashes(ws_id, "page", page_id, owner_id)

    assert [item["id"] for item in stashes] == [stash["id"]]


@pytest.mark.asyncio
async def test_folder_stash_inlines_folder_files(pool, monkeypatch):
    async def fake_file_url(storage_key, expires_in=3600):
        return f"https://files.test/{storage_key}?expires={expires_in}"

    monkeypatch.setattr(stash_service.storage_service, "get_file_url", fake_file_url)

    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)
    await _make_file(pool, ws_id, owner_id, folder_id=folder_id, name="brief.pdf")
    stash = await _make_stash(ws_id, owner_id, "workspace", "folder", folder_id)

    items = await stash_service.inline_items(stash, owner_id)

    files = items[0]["inline"]["files"]
    assert [file["name"] for file in files] == ["brief.pdf"]
    assert files[0]["url"].startswith("https://files.test/")


@pytest.mark.asyncio
async def test_object_level_permission_mutators_are_not_routes(client: AsyncClient):
    api_key, _owner = await _register(client)
    workspace = (
        await client.post(
            "/api/v1/workspaces", json={"name": "No object shares"}, headers=_auth(api_key)
        )
    ).json()
    folder = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/folders",
            json={"name": "Docs"},
            headers=_auth(api_key),
        )
    ).json()
    page = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/pages/new",
            json={"name": "Plan", "folder_id": folder["id"], "content": "Only Stashes share"},
            headers=_auth(api_key),
        )
    ).json()
    table = (
        await client.post(
            f"/api/v1/workspaces/{workspace['id']}/tables",
            json={"name": "Decisions", "columns": []},
            headers=_auth(api_key),
        )
    ).json()

    routes = [
        ("PATCH", f"/api/v1/objects/page/{page['id']}/permissions"),
        ("POST", f"/api/v1/objects/page/{page['id']}/shares"),
        ("DELETE", f"/api/v1/objects/page/{page['id']}/shares/{_owner['id']}"),
        ("POST", f"/api/v1/objects/page/{page['id']}/share-link"),
        ("PATCH", f"/api/v1/workspaces/{workspace['id']}/folders/{folder['id']}/permissions"),
        ("POST", f"/api/v1/workspaces/{workspace['id']}/folders/{folder['id']}/permissions/share"),
        ("PATCH", f"/api/v1/workspaces/{workspace['id']}/tables/{table['id']}/permissions"),
        ("POST", f"/api/v1/workspaces/{workspace['id']}/tables/{table['id']}/permissions/share"),
    ]
    for method, path in routes:
        resp = await client.request(method, path, headers=_auth(api_key), json={})
        assert resp.status_code == 404


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
