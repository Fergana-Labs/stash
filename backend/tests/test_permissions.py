"""Tests for Skill-mediated content access."""

import uuid

import pytest
from httpx import AsyncClient

from backend.models import SkillItem
from backend.services import (
    permission_service,
    session_folder_service,
    share_service,
    shared_skill_service,
)

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


async def _make_skill(workspace_id, owner_id, access, object_type, object_id):
    workspace_permission, public_permission = _permissions_for_access(access)
    return await shared_skill_service.create_skill(
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=f"{access} Skill",
        description="",
        workspace_permission=workspace_permission,
        public_permission=public_permission,
        discoverable=False,
        cover_image_url=None,
        items=[SkillItem(object_type=object_type, object_id=object_id)],
    )


def _permissions_for_access(access):
    if access == "private":
        return "none", "none"
    if access == "public":
        return "read", "read"
    return "read", "none"


async def _add_skill_member(pool, skill_id, user_id, granted_by, permission="read"):
    await pool.execute(
        "INSERT INTO skill_members (skill_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, $3, $4)",
        skill_id,
        user_id,
        permission,
        granted_by,
    )


# --- New model: private by default; owner + shares + skill-open ---


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
    # Viewers can comment (files_tree comment endpoints rely on this) but not write.
    assert await permission_service.check_access("page", page, viewer, require="comment")
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
async def test_table_share_by_email_grants_direct_read(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    table = await _make_table(pool, ws, owner, name="prospects")
    await pool.execute(
        "UPDATE users SET email = 'friend@example.com' WHERE id = $1",
        friend,
    )

    await share_service.share_with_user_by_email(
        object_type="table",
        object_id=table,
        email="friend@example.com",
        permission="read",
        owner_id=owner,
    )

    assert await permission_service.check_access("table", table, friend)
    assert not await permission_service.check_access(
        "table",
        table,
        friend,
        require="write",
    )


@pytest.mark.asyncio
async def test_public_skill_grants_read_only(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _make_skill(ws, owner, "public", "page", page)
    assert await permission_service.check_access("page", page, stranger)
    assert await permission_service.check_access("page", page, None)
    assert not await permission_service.check_access("page", page, stranger, require="write")


@pytest.mark.asyncio
async def test_public_session_folder_grants_read_only(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    folder = await session_folder_service.create_folder(
        ws,
        owner,
        "Public Sessions",
        public_permission="read",
    )
    folder_id = uuid.UUID(folder["id"])

    assert await permission_service.check_access("session_folder", folder_id, stranger)
    assert await permission_service.check_access("session_folder", folder_id, None)
    assert not await permission_service.check_access(
        "session_folder", folder_id, stranger, require="write"
    )
    assert not await permission_service.check_access(
        "session_folder", folder_id, None, require="write"
    )


@pytest.mark.asyncio
async def test_private_skill_member_reads_contents_not_write(pool):
    owner = await _make_user(pool)
    member = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    skill = await _make_skill(ws, owner, "private", "page", page)
    await _add_skill_member(pool, skill["id"], member, owner, "read")
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
async def test_viewer_cannot_create_private_stash_with_workspace_content(
    client: AsyncClient,
    pool,
):
    owner_key, _ = await _register(client)
    viewer_key, viewer = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(viewer["id"]), role="viewer")
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Spec", "content": "confidential"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    create = await client.post(
        f"/api/v1/workspaces/{ws}/skills",
        json={
            "title": "Private export",
            "workspace_permission": "none",
            "public_permission": "none",
            "items": [{"object_type": "page", "object_id": page_id}],
        },
        headers=_auth(viewer_key),
    )

    assert create.status_code == 403


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
        f"/api/v1/workspaces/{ws}/skills",
        json={
            "title": "Internal bundle",
            "items": [{"object_type": "page", "object_id": page_id}],
        },
        headers=_auth(editor_key),
    )

    assert create.status_code == 400
    assert "workspace owners" in create.json()["detail"]


@pytest.mark.asyncio
async def test_fork_respects_skill_creation_gates(client: AsyncClient, pool):
    """add-to-workspace writes forked pages into the workspace, so it obeys
    the same gates as creating a Skill: viewers cannot fork at all, and only
    workspace owners land a workspace-visible fork."""
    publisher_key, _ = await _register(client)
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    viewer_key, viewer = await _register(client)
    source_ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(publisher_key))).json()[
        "workspaces"
    ][0]["id"]
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{source_ws}/pages/new",
            json={"name": "Guide", "content": "published guide"},
            headers=_auth(publisher_key),
        )
    ).json()["id"]
    skill = (
        await client.post(
            f"/api/v1/workspaces/{source_ws}/skills",
            json={
                "title": "Public bundle",
                "workspace_permission": "none",
                "public_permission": "read",
                "items": [{"object_type": "page", "object_id": page_id}],
            },
            headers=_auth(publisher_key),
        )
    ).json()
    target_ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(target_ws), uuid.UUID(editor["id"]), role="editor")
    await _add_workspace_member(pool, uuid.UUID(target_ws), uuid.UUID(viewer["id"]), role="viewer")
    owner_ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "Owner fork target"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    viewer_fork = await client.post(
        f"/api/v1/skills/{skill['slug']}/add-to-workspace",
        json={"workspace_id": target_ws},
        headers=_auth(viewer_key),
    )
    editor_fork = await client.post(
        f"/api/v1/skills/{skill['slug']}/add-to-workspace",
        json={"workspace_id": target_ws},
        headers=_auth(editor_key),
    )
    owner_fork = await client.post(
        f"/api/v1/skills/{skill['slug']}/add-to-workspace",
        json={"workspace_id": owner_ws},
        headers=_auth(owner_key),
    )

    assert viewer_fork.status_code == 403
    assert editor_fork.status_code == 201
    assert editor_fork.json()["workspace_permission"] == "none"
    assert owner_fork.status_code == 201
    assert owner_fork.json()["workspace_permission"] == "read"


@pytest.mark.asyncio
async def test_skill_admin_can_edit_metadata_of_already_public_skill(
    client: AsyncClient,
    pool,
):
    # The owner gate guards visibility escalation only; metadata edits of an
    # already-shared Skill stay open to any skill admin.
    owner_key, owner = await _register(client)
    admin_key, admin = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    skill_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={"title": "Handbook", "workspace_permission": "none", "public_permission": "read"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    await _add_skill_member(
        pool,
        uuid.UUID(skill_id),
        uuid.UUID(admin["id"]),
        granted_by=uuid.UUID(owner["id"]),
        permission="admin",
    )

    rename = await client.patch(
        f"/api/v1/skills/{skill_id}",
        json={"title": "Handbook v2"},
        headers=_auth(admin_key),
    )

    assert rename.status_code == 200
    assert rename.json()["title"] == "Handbook v2"


@pytest.mark.asyncio
async def test_skill_admin_cannot_escalate_skill_visibility(client: AsyncClient, pool):
    owner_key, owner = await _register(client)
    admin_key, admin = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    skill_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={"title": "Drafts", "workspace_permission": "none", "public_permission": "none"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    await _add_skill_member(
        pool,
        uuid.UUID(skill_id),
        uuid.UUID(admin["id"]),
        granted_by=uuid.UUID(owner["id"]),
        permission="admin",
    )

    publish = await client.patch(
        f"/api/v1/skills/{skill_id}",
        json={"public_permission": "read"},
        headers=_auth(admin_key),
    )

    assert publish.status_code == 400
    assert "workspace owners" in publish.json()["detail"]


@pytest.mark.asyncio
async def test_public_write_skill_requests_are_rejected(client: AsyncClient):
    owner_key, _ = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Spec", "content": "confidential"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    item = {"object_type": "page", "object_id": page_id}

    create = await client.post(
        f"/api/v1/workspaces/{ws}/skills",
        json={"title": "Editable link", "public_permission": "write", "items": [item]},
        headers=_auth(owner_key),
    )
    publish = await client.post(
        f"/api/v1/workspaces/{ws}/skills/publish",
        json={"title": "Editable link", "public_permission": "write", "items": [item]},
        headers=_auth(owner_key),
    )
    skill = (
        await client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={"title": "Read-only link", "public_permission": "read", "items": [item]},
            headers=_auth(owner_key),
        )
    ).json()
    update = await client.patch(
        f"/api/v1/skills/{skill['id']}",
        json={"public_permission": "write"},
        headers=_auth(owner_key),
    )

    assert create.status_code == 422
    assert publish.status_code == 422
    assert update.status_code == 422


@pytest.mark.asyncio
async def test_workspace_write_stash_does_not_let_viewers_create_pages(
    client: AsyncClient,
    pool,
):
    owner_key, _ = await _register(client)
    viewer_key, viewer = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(viewer["id"]), role="viewer")
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Spec", "content": "confidential"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    stash = (
        await client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={
                "title": "Workspace Write",
                "workspace_permission": "write",
                "items": [{"object_type": "page", "object_id": page_id}],
            },
            headers=_auth(owner_key),
        )
    ).json()

    viewer_create = await client.post(
        f"/api/v1/skills/{stash['id']}/shared-pages",
        json={"name": "Viewer Draft", "content": "viewer should not write"},
        headers=_auth(viewer_key),
    )
    created_by_viewer = await pool.fetchval(
        "SELECT COUNT(*) FROM pages "
        "WHERE workspace_id = $1 AND metadata->>'shared_in_skill_id' = $2",
        uuid.UUID(ws),
        stash["id"],
    )
    editor_create = await client.post(
        f"/api/v1/skills/{stash['id']}/shared-pages",
        json={"name": "Editor Draft", "content": "editor can write"},
        headers=_auth(editor_key),
    )

    assert viewer_create.status_code == 403
    assert created_by_viewer == 0
    assert editor_create.status_code == 201


@pytest.mark.asyncio
async def test_stash_write_membership_requires_workspace_write_role(
    client: AsyncClient,
    pool,
):
    owner_key, _ = await _register(client)
    viewer_key, viewer = await _register(client)
    external_key, external = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(viewer["id"]), role="viewer")
    page_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/pages/new",
            json={"name": "Spec", "content": "confidential"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    stash = (
        await client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={
                "title": "Private Stash",
                "workspace_permission": "none",
                "public_permission": "none",
                "items": [{"object_type": "page", "object_id": page_id}],
            },
            headers=_auth(owner_key),
        )
    ).json()

    viewer_grant = await client.post(
        f"/api/v1/skills/{stash['id']}/members",
        json={"user_id": viewer["id"], "permission": "write"},
        headers=_auth(owner_key),
    )
    external_grant = await client.post(
        f"/api/v1/skills/{stash['id']}/members",
        json={"user_id": external["id"], "permission": "write"},
        headers=_auth(owner_key),
    )
    await pool.execute(
        "INSERT INTO skill_members (skill_id, user_id, permission, granted_by) "
        "VALUES ($1, $2, 'write', $3), ($1, $4, 'write', $3)",
        uuid.UUID(stash["id"]),
        uuid.UUID(viewer["id"]),
        uuid.UUID(external["id"]),
        uuid.UUID(external["id"]),
    )

    viewer_create = await client.post(
        f"/api/v1/skills/{stash['id']}/shared-pages",
        json={"name": "Viewer Draft", "content": "viewer should not write"},
        headers=_auth(viewer_key),
    )
    external_create = await client.post(
        f"/api/v1/skills/{stash['id']}/shared-pages",
        json={"name": "External Draft", "content": "external should not write"},
        headers=_auth(external_key),
    )

    assert viewer_grant.status_code == 403
    assert external_grant.status_code == 403
    assert viewer_create.status_code == 403
    assert external_create.status_code == 403


@pytest.mark.asyncio
async def test_non_owner_stash_admin_cannot_grant_external_member(
    client: AsyncClient,
    pool,
):
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    external_key, external = await _register(client)
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
    stash = (
        await client.post(
            f"/api/v1/workspaces/{ws}/skills",
            json={
                "title": "Private Stash",
                "workspace_permission": "none",
                "public_permission": "none",
                "items": [{"object_type": "page", "object_id": page_id}],
            },
            headers=_auth(owner_key),
        )
    ).json()
    admin_grant = await client.post(
        f"/api/v1/skills/{stash['id']}/members",
        json={"user_id": editor["id"], "permission": "admin"},
        headers=_auth(owner_key),
    )

    external_grant = await client.post(
        f"/api/v1/skills/{stash['id']}/members",
        json={"user_id": external["id"], "permission": "read"},
        headers=_auth(editor_key),
    )
    external_read = await client.get(
        f"/api/v1/skills/{stash['slug']}",
        headers=_auth(external_key),
    )

    assert admin_grant.status_code == 201
    assert external_grant.status_code == 403
    assert external_read.status_code == 404


@pytest.mark.asyncio
async def test_public_write_session_folder_requests_are_rejected(client: AsyncClient):
    owner_key, _ = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]

    create = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders",
        json={"name": "Editable sessions", "public_permission": "write"},
        headers=_auth(owner_key),
    )

    assert create.status_code == 422


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
async def test_editor_can_create_folders_but_cannot_publish(
    client: AsyncClient,
    pool,
):
    """Editors create workspace-visible folders every day ("New folder" sends
    just {name}), so that must work; only exposure beyond the workspace —
    public or discoverable — is owner-only, at create and at publish time."""
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")

    workspace_visible = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders",
        json={"name": "Workspace-visible"},
        headers=_auth(editor_key),
    )
    public_visible = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders",
        json={"name": "Public-visible", "public_permission": "read"},
        headers=_auth(editor_key),
    )
    rename_workspace = await client.patch(
        f"/api/v1/workspaces/{ws}/session-folders/{workspace_visible.json()['id']}",
        json={"name": "Renamed workspace-visible"},
        headers=_auth(editor_key),
    )
    publish_workspace = await client.patch(
        f"/api/v1/workspaces/{ws}/session-folders/{workspace_visible.json()['id']}",
        json={"public_permission": "read"},
        headers=_auth(editor_key),
    )

    assert workspace_visible.status_code == 200
    assert public_visible.status_code == 403
    assert rename_workspace.status_code == 200
    assert publish_workspace.status_code == 403


@pytest.mark.asyncio
async def test_downgraded_session_folder_owner_cannot_manage_folder(
    client: AsyncClient,
    pool,
):
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")
    folder = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders",
        json={
            "name": "Private owner folder",
            "workspace_permission": "none",
            "public_permission": "none",
        },
        headers=_auth(editor_key),
    )
    assert folder.status_code == 200
    folder_id = uuid.UUID(folder.json()["id"])
    await pool.execute(
        "UPDATE workspace_members SET role = 'viewer' WHERE workspace_id = $1 AND user_id = $2",
        uuid.UUID(ws),
        uuid.UUID(editor["id"]),
    )

    update = await client.patch(
        f"/api/v1/workspaces/{ws}/session-folders/{folder_id}",
        json={"name": "Viewer update"},
        headers=_auth(editor_key),
    )
    delete = await client.delete(
        f"/api/v1/workspaces/{ws}/session-folders/{folder_id}",
        headers=_auth(editor_key),
    )

    assert not await permission_service.check_access(
        "session_folder",
        folder_id,
        uuid.UUID(editor["id"]),
        require="write",
    )
    assert update.status_code == 404
    assert delete.status_code == 404


@pytest.mark.asyncio
async def test_session_folder_write_access_cannot_manage_folder(client: AsyncClient):
    owner_key, _ = await _register(client)
    stranger_key, _ = await _register(client)
    writer_key, _ = await _register_with_email(client, "session-folder-writer@example.com")
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    public_folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/session-folders",
            json={"name": "Public Read", "public_permission": "read"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    shared_folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/session-folders",
            json={"name": "Shared Write"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "session_folder",
            "object_id": shared_folder_id,
            "email": "session-folder-writer@example.com",
            "permission": "write",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    public_update = await client.patch(
        f"/api/v1/workspaces/{ws}/session-folders/{public_folder_id}",
        json={"name": "Renamed"},
        headers=_auth(stranger_key),
    )
    shared_delete = await client.delete(
        f"/api/v1/workspaces/{ws}/session-folders/{shared_folder_id}",
        headers=_auth(writer_key),
    )

    assert public_update.status_code == 404
    assert shared_delete.status_code == 404


@pytest.mark.asyncio
async def test_editor_cannot_add_sessions_to_public_session_folder(
    client: AsyncClient,
    pool,
):
    """Adding a session to a public folder publishes it, so that stays
    owner-only for editors on both the direct-upsert and assign paths."""
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")
    public_folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/session-folders",
            json={"name": "Published transcripts", "public_permission": "read"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    direct_upsert = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={
            "session_id": "editor-public-direct",
            "agent_name": "codex",
            "session_folder_id": public_folder_id,
        },
        headers=_auth(editor_key),
    )
    session = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "editor-private-session", "agent_name": "codex"},
        headers=_auth(editor_key),
    )
    assign = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders/assign",
        json={"session_row_ids": [session.json()["id"]], "folder_id": public_folder_id},
        headers=_auth(editor_key),
    )

    assert direct_upsert.status_code == 404
    assert session.status_code == 201
    assert assign.status_code == 404
    assert not await pool.fetchval(
        "SELECT 1 FROM sessions WHERE workspace_id = $1 AND session_id = $2",
        uuid.UUID(ws),
        "editor-public-direct",
    )
    assert await pool.fetchval(
        "SELECT session_folder_id FROM sessions WHERE id = $1",
        uuid.UUID(session.json()["id"]),
    ) != uuid.UUID(public_folder_id)


@pytest.mark.asyncio
async def test_editor_can_file_sessions_into_workspace_folder(client: AsyncClient, pool):
    """Workspace-visible folders are the everyday team folders that plugin
    uploads pin via the repo manifest — editors must be able to file sessions
    into them on both the direct-upsert and assign paths."""
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")
    team_folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/session-folders",
            json={"name": "Team transcripts"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    direct_upsert = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={
            "session_id": "editor-team-direct",
            "agent_name": "codex",
            "session_folder_id": team_folder_id,
        },
        headers=_auth(editor_key),
    )
    session = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "editor-team-assign", "agent_name": "codex"},
        headers=_auth(editor_key),
    )
    assign = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders/assign",
        json={"session_row_ids": [session.json()["id"]], "folder_id": team_folder_id},
        headers=_auth(editor_key),
    )

    assert direct_upsert.status_code in (200, 201)
    assert assign.status_code == 200
    assert await pool.fetchval(
        "SELECT session_folder_id FROM sessions WHERE id = $1",
        uuid.UUID(session.json()["id"]),
    ) == uuid.UUID(team_folder_id)


@pytest.mark.asyncio
async def test_workspace_editor_can_manage_session_folders(client: AsyncClient, pool):
    """Removing public/shared write links must not strip workspace editors of
    folder rename/delete — the workspace is the trust boundary and the UI
    shows these controls to every member."""
    owner_key, _ = await _register(client)
    editor_key, editor = await _register(client)
    ws = (await client.get("/api/v1/workspaces/mine", headers=_auth(owner_key))).json()[
        "workspaces"
    ][0]["id"]
    await _add_workspace_member(pool, uuid.UUID(ws), uuid.UUID(editor["id"]), role="editor")
    folder_id = (
        await client.post(
            f"/api/v1/workspaces/{ws}/session-folders",
            json={"name": "Team Deploys"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    rename = await client.patch(
        f"/api/v1/workspaces/{ws}/session-folders/{folder_id}",
        json={"name": "Renamed by editor"},
        headers=_auth(editor_key),
    )
    delete = await client.delete(
        f"/api/v1/workspaces/{ws}/session-folders/{folder_id}",
        headers=_auth(editor_key),
    )

    assert rename.status_code == 200
    assert rename.json()["name"] == "Renamed by editor"
    assert delete.status_code == 204


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
    direct_upsert = await client.post(
        f"/api/v1/workspaces/{first_ws}/sessions",
        json={
            "session_id": "cross-workspace-direct",
            "agent_name": "codex",
            "session_folder_id": second_folder_id,
        },
        headers=_auth(first_key),
    )
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

    assert direct_upsert.status_code == 404
    assert assign.status_code == 404


@pytest.mark.asyncio
async def test_session_folder_assign_batch_is_all_or_nothing(client: AsyncClient, pool):
    # A 404 on a mixed batch must mean nothing moved — otherwise the client's
    # view and the server state silently diverge.
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
        json={"session_id": "batch-1", "agent_name": "codex"},
        headers=_auth(owner_key),
    )
    assert session.status_code == 201
    valid_id = session.json()["id"]
    before = await pool.fetchrow(
        "SELECT session_folder_id FROM sessions WHERE id = $1", uuid.UUID(valid_id)
    )

    assign = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders/assign",
        json={"session_row_ids": [valid_id, str(uuid.uuid4())], "folder_id": folder_id},
        headers=_auth(owner_key),
    )

    assert assign.status_code == 404
    after = await pool.fetchrow(
        "SELECT session_folder_id FROM sessions WHERE id = $1", uuid.UUID(valid_id)
    )
    assert after["session_folder_id"] == before["session_folder_id"]


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
async def test_revoked_pending_share_invite_does_not_convert_on_signup(client: AsyncClient):
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

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "revoked-newcomer@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    revoked = await client.request(
        "DELETE",
        "/api/v1/share/invite",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "REVOKED-NEWCOMER@example.com",
        },
        headers=_auth(owner_key),
    )
    listing = await client.get(
        f"/api/v1/share?object_type=page&object_id={page_id}",
        headers=_auth(owner_key),
    )
    newcomer_key, _ = await _register_with_email(
        client,
        "revoked-newcomer@example.com",
    )

    assert share.status_code == 200
    assert share.json()["pending"] is True
    assert revoked.status_code == 200
    assert listing.status_code == 200
    assert listing.json()["shares"] == []
    assert (
        await client.get(
            f"/api/v1/workspaces/{ws}/pages/{page_id}",
            headers=_auth(newcomer_key),
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_expired_pending_share_invite_does_not_convert_on_signup(client: AsyncClient, pool):
    """A time-bounded invite must not grant anything if the recipient signs up
    after the expiry — otherwise an expired invite would silently become
    permanent access."""
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

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "late-newcomer@example.com",
            "permission": "read",
            "expires_at": "2020-01-01T00:00:00Z",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200
    assert share.json()["pending"] is True

    newcomer_key, _ = await _register_with_email(client, "late-newcomer@example.com")

    assert (
        await client.get(
            f"/api/v1/workspaces/{ws}/pages/{page_id}",
            headers=_auth(newcomer_key),
        )
    ).status_code == 404
    # The expired invite is dropped, not left around to convert later.
    remaining = await pool.fetchval(
        "SELECT count(*) FROM share_invites WHERE lower(email) = 'late-newcomer@example.com'"
    )
    assert remaining == 0


@pytest.mark.asyncio
async def test_converted_share_keeps_invite_expiry(client: AsyncClient, pool):
    """When a pending invite converts on signup, the resulting share carries
    the invite's expires_at — conversion must not upgrade a time-bounded grant
    to a permanent one."""
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

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "timed-newcomer@example.com",
            "permission": "read",
            "expires_at": "2099-01-01T00:00:00Z",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200
    assert share.json()["pending"] is True

    newcomer_key, newcomer = await _register_with_email(client, "timed-newcomer@example.com")

    assert (
        await client.get(
            f"/api/v1/workspaces/{ws}/pages/{page_id}",
            headers=_auth(newcomer_key),
        )
    ).status_code == 200
    expires_at = await pool.fetchval(
        "SELECT expires_at FROM shares WHERE object_type = 'page' AND object_id = $1 "
        "AND principal_type = 'user' AND principal_id = $2",
        uuid.UUID(page_id),
        uuid.UUID(newcomer["id"]),
    )
    assert expires_at is not None
    assert expires_at.year == 2099


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
