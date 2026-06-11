"""Tests for Stash-mediated content access."""

import uuid

import pytest
from httpx import AsyncClient

from backend.models import CartridgeItem
from backend.services import cartridge_service, permission_service, share_service

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


async def _register_with_email(client: AsyncClient, email: str) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1", "email": email},
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


async def _make_page(
    pool, workspace_id, created_by, folder_id=None, name="page", content="content"
):
    row = await pool.fetchrow(
        "INSERT INTO pages (workspace_id, folder_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        workspace_id,
        folder_id,
        name,
        content,
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


async def _make_table(pool, workspace_id, created_by, folder_id=None, name="table"):
    row = await pool.fetchrow(
        "INSERT INTO tables (workspace_id, folder_id, name, created_by) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        workspace_id,
        folder_id,
        name,
        created_by,
    )
    return row["id"]


async def _make_file(
    pool, workspace_id, uploaded_by, folder_id=None, name="file.txt", content_type="text/plain"
):
    row = await pool.fetchrow(
        "INSERT INTO files "
        "(workspace_id, folder_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, 12, $5, $6) RETURNING id",
        workspace_id,
        folder_id,
        name,
        content_type,
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


async def _make_cartridge(workspace_id, owner_id, access, object_type, object_id):
    workspace_permission, public_permission = _permissions_for_access(access)
    return await cartridge_service.create_cartridge(
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=f"{access} Stash",
        description="",
        workspace_permission=workspace_permission,
        public_permission=public_permission,
        discoverable=False,
        cover_image_url=None,
        items=[CartridgeItem(object_type=object_type, object_id=object_id)],
    )


def _permissions_for_access(access):
    if access == "private":
        return "none", "none"
    if access == "public":
        return "read", "read"
    return "read", "none"


async def _add_cartridge_member(pool, cartridge_id, user_id, granted_by, permission="read"):
    await pool.execute(
        "INSERT INTO cartridge_members (cartridge_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, $3, $4)",
        cartridge_id,
        user_id,
        permission,
        granted_by,
    )


# --- New model: private by default; owner + shares + cartridge-open ---


async def _share(pool, ws_id, object_type, object_id, user_id, permission="read", by=None):
    await pool.execute(
        "INSERT INTO shares (workspace_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,$2,$3,'user',$4,$5,$6)",
        ws_id,
        object_type,
        object_id,
        user_id,
        permission,
        by or user_id,
    )


@pytest.mark.asyncio
async def test_owner_has_read_and_write(pool):
    owner = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    assert await permission_service.check_access("page", page, owner)
    assert await permission_service.check_access("page", page, owner, require="write")


@pytest.mark.asyncio
async def test_viewer_workspace_member_can_read_not_write(pool):
    owner = await _make_user(pool)
    viewer = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    await _add_workspace_member(pool, ws, viewer, role="viewer")
    page = await _make_page(pool, ws, owner)

    assert await permission_service.check_access("page", page, viewer)
    assert not await permission_service.check_access("page", page, viewer, require="write")


@pytest.mark.asyncio
async def test_stranger_denied_by_default(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    assert not await permission_service.check_access("page", page, stranger)
    assert not await permission_service.check_access("page", page, None)


@pytest.mark.asyncio
async def test_user_share_grants_read_not_write(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _share(pool, ws, "page", page, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    assert not await permission_service.check_access("page", page, friend, require="write")


@pytest.mark.asyncio
async def test_user_write_share_grants_write(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _share(pool, ws, "page", page, friend, "write", by=owner)
    assert await permission_service.check_access("page", page, friend, require="write")


@pytest.mark.asyncio
async def test_comment_tier_sits_between_read_and_write(pool):
    """read < comment < write: a read share can't comment; a comment share can
    comment but not write; a write share can do everything."""
    owner = await _make_user(pool)
    reader = await _make_user(pool)
    commenter = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _share(pool, ws, "page", page, reader, "read", by=owner)
    await _share(pool, ws, "page", page, commenter, "comment", by=owner)

    # read share: can read, cannot comment, cannot write.
    assert await permission_service.check_access("page", page, reader)
    assert not await permission_service.check_access("page", page, reader, require="comment")
    assert not await permission_service.check_access("page", page, reader, require="write")
    # comment share: can read + comment, not write.
    assert await permission_service.check_access("page", page, commenter, require="comment")
    assert not await permission_service.check_access("page", page, commenter, require="write")


@pytest.mark.asyncio
async def test_expired_share_grants_nothing(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await pool.execute(
        "INSERT INTO shares (workspace_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by, expires_at) "
        "VALUES ($1,'page',$2,'user',$3,'write',$4, now() - interval '1 hour')",
        ws,
        page,
        friend,
        owner,
    )
    # Expired → no access, and absent from the readable predicate / with-me list.
    assert not await permission_service.check_access("page", page, friend)
    with_me = await share_service.list_shared_with_user(friend)
    assert all(item["object_id"] != str(page) for item in with_me)


@pytest.mark.asyncio
async def test_future_expiry_still_grants(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await pool.execute(
        "INSERT INTO shares (workspace_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by, expires_at) "
        "VALUES ($1,'page',$2,'user',$3,'read',$4, now() + interval '1 day')",
        ws,
        page,
        friend,
        owner,
    )
    assert await permission_service.check_access("page", page, friend)


@pytest.mark.asyncio
async def test_folder_share_cascades_to_children(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    folder = await _make_folder(pool, ws, owner)
    page = await _make_page(pool, ws, owner, folder_id=folder)
    file_id = await _make_file(pool, ws, owner, folder_id=folder)
    table = await _make_table(pool, ws, owner, folder_id=folder)
    await _share(pool, ws, "folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    assert await permission_service.check_access("file", file_id, friend)
    assert await permission_service.check_access("table", table, friend)


@pytest.mark.asyncio
async def test_table_folder_share_cascades_and_write_inherits(pool):
    """A table inside a shared folder inherits the folder's grant — read from a
    read share, write from a write share — just like pages and files. A table
    at the workspace root is unaffected by the folder share."""
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    folder = await _make_folder(pool, ws, owner)
    table = await _make_table(pool, ws, owner, folder_id=folder)
    root_table = await _make_table(pool, ws, owner, name="root-table")

    # Before any share the non-member can't see either table.
    assert not await permission_service.check_access("table", table, friend)

    await _share(pool, ws, "folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("table", table, friend)
    # Read share is not a write grant, and the root table is outside the folder.
    assert not await permission_service.check_access("table", table, friend, require="write")
    assert not await permission_service.check_access("table", root_table, friend)

    # Upgrading the folder share to write cascades write to the table.
    await pool.execute(
        "UPDATE shares SET permission='write' WHERE object_type='folder' "
        "AND object_id=$1 AND principal_id=$2",
        folder,
        friend,
    )
    assert await permission_service.check_access("table", table, friend, require="write")


@pytest.mark.asyncio
async def test_public_cartridge_grants_read_only(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _make_cartridge(ws, owner, "public", "page", page)
    assert await permission_service.check_access("page", page, stranger)
    assert await permission_service.check_access("page", page, None)
    assert not await permission_service.check_access("page", page, stranger, require="write")


@pytest.mark.asyncio
async def test_private_cartridge_member_reads_contents_not_write(pool):
    owner = await _make_user(pool)
    member = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    cartridge = await _make_cartridge(ws, owner, "private", "page", page)
    await _add_cartridge_member(pool, cartridge["id"], member, owner, "read")
    assert await permission_service.check_access("page", page, member)
    assert not await permission_service.check_access("page", page, member, require="write")
    assert not await permission_service.check_access("page", page, stranger)


@pytest.mark.asyncio
async def test_share_then_unshare_revokes(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _share(pool, ws, "page", page, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    await pool.execute(
        "DELETE FROM shares WHERE object_type='page' AND object_id=$1 AND principal_id=$2",
        page,
        friend,
    )
    assert not await permission_service.check_access("page", page, friend)


@pytest.mark.asyncio
async def test_session_folder_share_cascades_to_sessions(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    folder = await pool.fetchval(
        "INSERT INTO session_folders (workspace_id, owner_user_id, name, slug) "
        "VALUES ($1, $2, 'launch', 'launch-' || left(replace(gen_random_uuid()::text, '-', ''), 8)) "
        "RETURNING id",
        ws,
        owner,
    )
    session_row = await _make_session(pool, ws, owner, session_id="s-folder-1")
    await pool.execute(
        "UPDATE sessions SET session_folder_id = $2 WHERE id = $1", session_row, folder
    )
    # Not shared yet → friend denied.
    assert not await permission_service.check_access("session", session_row, friend)
    # Share the folder → cascades to the session.
    await _share(pool, ws, "session_folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("session", session_row, friend)


@pytest.mark.asyncio
async def test_share_by_email_grants_page_read_over_http(client: AsyncClient, pool):
    """The primary collaboration path, end-to-end through the REST API: a page
    is private to its owner until shared by email; the grantee (not a workspace
    member) then reads it, and a stranger still cannot.

    Regression for the single-item read endpoints gating on workspace
    membership and so ignoring shares."""
    owner_key, _ = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Plan", "content": "private roadmap"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    grantee_key, grantee = await _register(client)
    await pool.execute(
        "UPDATE users SET email = 'grantee@example.com' WHERE id = $1", grantee["id"]
    )
    stranger_key, _ = await _register(client)

    page_url = f"/api/v1/workspaces/{ws}/pages/{page_id}"
    assert (await client.get(page_url, headers=_auth(owner_key))).status_code == 200
    # Private before any share.
    assert (await client.get(page_url, headers=_auth(grantee_key))).status_code == 404

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "grantee@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    # The share grants the non-member read access; the stranger is still denied.
    assert (await client.get(page_url, headers=_auth(grantee_key))).status_code == 200
    assert (await client.get(page_url, headers=_auth(stranger_key))).status_code == 404


@pytest.mark.asyncio
async def test_unshared_file_read_returns_forbidden_over_http(client: AsyncClient, pool):
    owner_key, owner = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    file_id = await _make_file(pool, uuid.UUID(ws), uuid.UUID(owner["id"]))
    stranger_key, _ = await _register(client)

    file_url = f"/api/v1/workspaces/{ws}/files/{file_id}"
    denied = await client.get(file_url, headers=_auth(stranger_key))
    assert denied.status_code == 403
    assert denied.json()["detail"] == "You don't have access to this file"

    missing = await client.get(
        f"/api/v1/workspaces/{ws}/files/{uuid.uuid4()}",
        headers=_auth(owner_key),
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "File not found"


@pytest.mark.asyncio
async def test_folder_share_by_email_allows_non_member_browse_over_http(client: AsyncClient):
    """Folder shares must let a non-member open the shared folder and see the
    readable children; otherwise the folder cascade only works for known child
    URLs, which is not a usable share."""
    owner_key, _ = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/folders",
            json={"name": "Specs"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    subfolder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/folders",
            json={"name": "Archive", "parent_folder_id": folder_id},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"folder_id": folder_id, "name": "Roadmap", "content": "Q3 plan"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    grantee_key, _ = await _register_with_email(client, "folder-grantee@example.com")

    folder_url = f"/api/v1/workspaces/{ws}/folders/{folder_id}"
    contents_url = f"{folder_url}/contents"
    assert (await client.get(folder_url, headers=_auth(grantee_key))).status_code == 404

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "folder",
            "object_id": folder_id,
            "email": "folder-grantee@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    folder = await client.get(folder_url, headers=_auth(grantee_key))
    assert folder.status_code == 200
    contents = await client.get(contents_url, headers=_auth(grantee_key))
    assert contents.status_code == 200
    assert {p["id"] for p in contents.json()["pages"]} == {page_id}
    assert {f["id"] for f in contents.json()["subfolders"]} == {subfolder_id}


@pytest.mark.asyncio
async def test_write_share_by_email_allows_non_member_page_update_over_http(
    client: AsyncClient,
):
    """A write share should authorize the object write route directly; workspace
    membership is ownership, not a prerequisite for a user share."""
    owner_key, _ = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Draft", "content": "before"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    writer_key, _ = await _register_with_email(client, "writer@example.com")

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "writer@example.com",
            "permission": "write",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    update = await client.patch(
        f"/api/v1/workspaces/{ws}/pages/{page_id}",
        json={"content": "after"},
        headers=_auth(writer_key),
    )
    assert update.status_code == 200
    assert update.json()["content_markdown"] == "after"


@pytest.mark.asyncio
async def test_non_owner_workspace_member_cannot_share_page_over_http(
    client: AsyncClient,
    pool,
):
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Spec", "content": "confidential"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "external@example.com",
            "permission": "read",
        },
        headers=_auth(editor_key),
    )

    assert share.status_code == 404


@pytest.mark.asyncio
async def test_non_owner_workspace_member_cannot_create_workspace_visible_stash(
    client: AsyncClient,
    pool,
):
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Spec", "content": "confidential"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    create = await client.post(
        f"/api/v1/workspaces/{ws}/cartridges",
        json={
            "title": "Internal bundle",
            "items": [{"object_type": "page", "object_id": page_id}],
        },
        headers=_auth(editor_key),
    )

    assert create.status_code == 403


@pytest.mark.asyncio
async def test_session_folder_share_by_email_lists_for_non_member(client: AsyncClient):
    owner_key, _ = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/session-folders",
            json={"name": "Deploys"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    session = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "deploy-1", "agent_name": "codex"},
        headers=_auth(owner_key),
    )
    assert session.status_code == 201
    assigned = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders/assign",
        json={"session_row_ids": [session.json()["id"]], "folder_id": folder_id},
        headers=_auth(owner_key),
    )
    assert assigned.status_code == 200

    grantee_key, _ = await _register_with_email(client, "session-folder-grantee@example.com")
    before = await client.get(
        f"/api/v1/workspaces/{ws}/session-folders",
        headers=_auth(grantee_key),
    )
    assert before.status_code == 200
    assert before.json()["folders"] == []

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "session_folder",
            "object_id": folder_id,
            "email": "session-folder-grantee@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    after = await client.get(
        f"/api/v1/workspaces/{ws}/session-folders",
        headers=_auth(grantee_key),
    )
    assert after.status_code == 200
    folders = after.json()["folders"]
    assert len(folders) == 1
    assert folders[0]["id"] == folder_id
    assert folders[0]["name"] == "Deploys"
    assert folders[0]["session_count"] == 1


@pytest.mark.asyncio
async def test_viewer_cannot_create_or_assign_session_folder(client: AsyncClient, pool):
    owner_key, _ = await _register(client)
    viewer_key, viewer = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(viewer["id"]), role="viewer")
    folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/session-folders",
            json={"name": "Deploys"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    session = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "viewer-denied-1", "agent_name": "codex"},
        headers=_auth(owner_key),
    )
    assert session.status_code == 201

    create = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders",
        json={"name": "Viewer Folder"},
        headers=_auth(viewer_key),
    )
    assign = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders/assign",
        json={"session_row_ids": [session.json()["id"]], "folder_id": folder_id},
        headers=_auth(viewer_key),
    )

    assert create.status_code == 403
    assert assign.status_code == 403


@pytest.mark.asyncio
async def test_session_folder_assign_rejects_cross_workspace_ids(client: AsyncClient):
    first_key, _ = await _register(client)
    second_key, _ = await _register(client)
    first_ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(first_key))).json()[
        "workspaces"
    ][0]["id"]
    second_ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(second_key))).json()[
        "workspaces"
    ][0]["id"]
    second_folder_id = (
        await client.post(
            f"/api/v1/workspaces/{second_ws}/session-folders",
            json={"name": "Other Workspace"},
            headers=_auth(second_key),
        )
    ).json()["id"]
    session = await client.post(
        f"/api/v1/workspaces/{first_ws}/sessions",
        json={"session_id": "cross-workspace-1", "agent_name": "codex"},
        headers=_auth(first_key),
    )
    assert session.status_code == 201

    assign = await client.post(
        f"/api/v1/workspaces/{first_ws}/session-folders/assign",
        json={"session_row_ids": [session.json()["id"]], "folder_id": second_folder_id},
        headers=_auth(first_key),
    )

    assert assign.status_code == 404


@pytest.mark.asyncio
async def test_share_by_email_pending_invite_converts_on_signup(client: AsyncClient):
    """Sharing to an email with no account yet records a pending invite that
    becomes a real share when that person signs up with the email."""
    owner_key, _ = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Spec", "content": "secret spec"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    # Share to an email that has no user — recorded as pending, not 404.
    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "newcomer@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200
    assert share.json()["pending"] is True

    # The owner sees it listed as a pending invite.
    listing = await client.get(
        f"/api/v1/share?object_type=page&object_id={page_id}", headers=_auth(owner_key)
    )
    pending = [s for s in listing.json()["shares"] if s["pending"]]
    assert [s["email"] for s in pending] == ["newcomer@example.com"]

    # The newcomer signs up with that email → invite converts → they can read.
    newcomer_key, _ = await _register_with_email(client, "newcomer@example.com")
    page_url = f"/api/v1/workspaces/{ws}/pages/{page_id}"
    assert (await client.get(page_url, headers=_auth(newcomer_key))).status_code == 200

    # The pending invite is gone; it's now a real (non-pending) share.
    after = await client.get(
        f"/api/v1/share?object_type=page&object_id={page_id}", headers=_auth(owner_key)
    )
    rows = after.json()["shares"]
    assert all(not s["pending"] for s in rows)
    assert any(s["email"] == "newcomer@example.com" for s in rows)


@pytest.mark.asyncio
async def test_shared_with_me_lists_incoming_not_outgoing(pool):
    from backend.services import share_service

    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    folder = await _make_folder(pool, ws, owner, name="Shared Folder")
    await _share(pool, ws, "folder", folder, friend, "write", by=owner)

    items = await share_service.list_shared_with_user(friend)
    match = [i for i in items if i["object_id"] == str(folder)]
    assert len(match) == 1
    assert match[0]["object_type"] == "folder"
    assert match[0]["name"] == "Shared Folder"
    assert match[0]["permission"] == "write"
    assert match[0]["workspace_id"] == str(ws)
    # The owner is on the giving end — nothing is shared *with* them.
    assert await share_service.list_shared_with_user(owner) == []


@pytest.mark.asyncio
async def test_shared_session_folder_sessions_gated_on_share(pool):
    from fastapi import HTTPException

    from backend.services import share_service

    owner = await _make_user(pool)
    friend = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    sf = await pool.fetchval(
        "INSERT INTO session_folders (workspace_id, owner_user_id, name, slug) "
        "VALUES ($1, $2, 'SF', 'sf-' || left(replace(gen_random_uuid()::text, '-', ''), 8)) "
        "RETURNING id",
        ws,
        owner,
    )
    session_row = await _make_session(pool, ws, owner, session_id="shared-sess-1")
    await pool.execute("UPDATE sessions SET session_folder_id = $2 WHERE id = $1", session_row, sf)
    await _share(pool, ws, "session_folder", sf, friend, "read", by=owner)

    rows = await share_service.list_shared_session_folder_sessions(sf, friend)
    assert [r["id"] for r in rows] == [str(session_row)]

    # A stranger with no share is denied.
    with pytest.raises(HTTPException):
        await share_service.list_shared_session_folder_sessions(sf, stranger)


@pytest.mark.asyncio
async def test_overview_counts_span_shared_not_unshared(pool):
    """The "Your brain" vitals (analytics_service.get_overview_counts) span the
    user's own content plus content shared with them — but a share only surfaces
    the specific shared rows, never the whole sharing workspace, and an unrelated
    user sees nothing. Guards the widened member∪shared prefilter against leaks."""
    from backend.services import analytics_service

    owner = await _make_user(pool)
    friend = await _make_user(pool)  # gets one folder shared
    stranger = await _make_user(pool)  # gets nothing
    ws = await _make_workspace(pool, owner)  # friend/stranger are NOT members
    folder = await _make_folder(pool, ws, owner)
    await _make_page(pool, ws, owner, folder_id=folder, name="shared-page")
    await _make_page(pool, ws, owner, name="private-root-page")
    await _share(pool, ws, "folder", folder, friend, "read", by=owner)

    owner_counts = await analytics_service.get_overview_counts(owner)
    friend_counts = await analytics_service.get_overview_counts(friend)
    stranger_counts = await analytics_service.get_overview_counts(stranger)

    # Owner sees both of its pages; friend sees only the page in the shared
    # folder (not the un-shared root page); stranger sees neither.
    assert owner_counts["pages"] >= 2
    assert friend_counts["pages"] == 1
    assert stranger_counts["pages"] == 0
