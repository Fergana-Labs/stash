"""Tests for Stash-mediated content access."""

import uuid

import pytest
from httpx import AsyncClient

from backend.models import CartridgeItem
from backend.services import cartridge_service, permission_service

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


async def _make_table(pool, workspace_id, created_by, name="table"):
    row = await pool.fetchrow(
        "INSERT INTO tables (workspace_id, name, created_by) VALUES ($1, $2, $3) RETURNING id",
        workspace_id,
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
        ws_id, object_type, object_id, user_id, permission, by or user_id,
    )


@pytest.mark.asyncio
async def test_owner_has_read_and_write(pool):
    owner = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    assert await permission_service.check_access("page", page, owner)
    assert await permission_service.check_access("page", page, owner, require_write=True)


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
    assert not await permission_service.check_access("page", page, friend, require_write=True)


@pytest.mark.asyncio
async def test_user_write_share_grants_write(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _share(pool, ws, "page", page, friend, "write", by=owner)
    assert await permission_service.check_access("page", page, friend, require_write=True)


@pytest.mark.asyncio
async def test_folder_share_cascades_to_children(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    folder = await _make_folder(pool, ws, owner)
    page = await _make_page(pool, ws, owner, folder_id=folder)
    file_id = await _make_file(pool, ws, owner, folder_id=folder)
    await _share(pool, ws, "folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    assert await permission_service.check_access("file", file_id, friend)


@pytest.mark.asyncio
async def test_public_cartridge_grants_read_only(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    page = await _make_page(pool, ws, owner)
    await _make_cartridge(ws, owner, "public", "page", page)
    assert await permission_service.check_access("page", page, stranger)
    assert await permission_service.check_access("page", page, None)
    assert not await permission_service.check_access("page", page, stranger, require_write=True)


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
    assert not await permission_service.check_access("page", page, member, require_write=True)
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
        page, friend,
    )
    assert not await permission_service.check_access("page", page, friend)


@pytest.mark.asyncio
async def test_session_folder_share_cascades_to_sessions(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    folder = await pool.fetchval(
        "INSERT INTO session_folders (workspace_id, owner_user_id, name) "
        "VALUES ($1, $2, 'launch') RETURNING id",
        ws, owner,
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
