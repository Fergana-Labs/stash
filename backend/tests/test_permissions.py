"""Tests for the permission service — visibility modes and write-access logic."""

import uuid

import pytest

from backend.services import permission_service

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
        "INSERT INTO tables (workspace_id, name, created_by) " "VALUES ($1, $2, $3) RETURNING id",
        workspace_id,
        name,
        created_by,
    )
    return row["id"]


@pytest.mark.asyncio
async def test_owner_has_access(pool):
    user_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, user_id)
    folder_id = await _make_folder(pool, ws_id, user_id)

    assert await permission_service.check_access("folder", folder_id, user_id, workspace_id=ws_id)
    assert await permission_service.check_access(
        "folder", folder_id, user_id, workspace_id=ws_id, require_write=True
    )


@pytest.mark.asyncio
async def test_member_read_inherit(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    folder_id = await _make_folder(pool, ws_id, owner_id)

    assert await permission_service.check_access("folder", folder_id, member_id, workspace_id=ws_id)


@pytest.mark.asyncio
async def test_member_cannot_write_without_share(pool):
    """Members get read access by default but writing requires an explicit share."""
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    folder_id = await _make_folder(pool, ws_id, owner_id)

    result = await permission_service.check_access(
        "folder", folder_id, member_id, workspace_id=ws_id, require_write=True
    )
    assert not result


@pytest.mark.asyncio
async def test_member_can_write_with_share(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    folder_id = await _make_folder(pool, ws_id, owner_id)

    await permission_service.add_share("folder", folder_id, member_id, "write", owner_id)
    result = await permission_service.check_access(
        "folder", folder_id, member_id, workspace_id=ws_id, require_write=True
    )
    assert result


@pytest.mark.asyncio
async def test_non_member_denied(pool):
    owner_id = await _make_user(pool)
    stranger_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)

    assert not await permission_service.check_access(
        "folder", folder_id, stranger_id, workspace_id=ws_id
    )


@pytest.mark.asyncio
async def test_public_visibility_readable_by_anyone(pool):
    owner_id = await _make_user(pool)
    stranger_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)

    await permission_service.set_visibility("folder", folder_id, "public")
    assert await permission_service.check_access("folder", folder_id, stranger_id)


@pytest.mark.asyncio
async def test_private_visibility_denies_member(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    folder_id = await _make_folder(pool, ws_id, owner_id)

    await permission_service.set_visibility("folder", folder_id, "private")
    assert not await permission_service.check_access(
        "folder", folder_id, member_id, workspace_id=ws_id
    )


@pytest.mark.asyncio
async def test_private_tag_keeps_creator_access(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    page_id = await _make_page(pool, ws_id, owner_id)

    await permission_service.set_privacy_visibility("page", page_id, "private", owner_id)

    assert await permission_service.check_access("page", page_id, owner_id, workspace_id=ws_id)
    assert not await permission_service.check_access("page", page_id, member_id, workspace_id=ws_id)


@pytest.mark.asyncio
async def test_session_privacy_tag_limits_workspace_members(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    session_row_id = await _make_session(pool, ws_id, owner_id)

    await permission_service.set_privacy_visibility("session", session_row_id, "private", owner_id)

    assert await permission_service.check_access(
        "session", session_row_id, owner_id, workspace_id=ws_id
    )
    assert not await permission_service.check_access(
        "session", session_row_id, member_id, workspace_id=ws_id
    )


@pytest.mark.asyncio
async def test_table_visibility_uses_privacy_tags(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    table_id = await _make_table(pool, ws_id, owner_id)

    await permission_service.set_visibility("table", table_id, "private")

    tag = await pool.fetchrow(
        "SELECT pt.access FROM privacy_tags pt "
        "JOIN privacy_tag_objects pto ON pto.tag_id = pt.id "
        "WHERE pto.object_type = 'table' AND pto.object_id = $1",
        table_id,
    )

    assert tag["access"] == "members"
    assert not await permission_service.check_access(
        "table", table_id, member_id, workspace_id=ws_id
    )


@pytest.mark.asyncio
async def test_history_share_uses_privacy_tag_members(pool):
    owner_id = await _make_user(pool)
    reader_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    event_id = await pool.fetchval(
        "INSERT INTO history_events (workspace_id, created_by, agent_name, event_type, content) "
        "VALUES ($1, $2, 'agent', 'message', 'hello') RETURNING id",
        ws_id,
        owner_id,
    )

    await permission_service.set_visibility("history", event_id, "private")
    await permission_service.add_share("history", event_id, reader_id, "read", owner_id)

    tag_member = await pool.fetchrow(
        "SELECT ptm.permission FROM privacy_tag_members ptm "
        "JOIN privacy_tag_objects pto ON pto.tag_id = ptm.tag_id "
        "WHERE pto.object_type = 'history' AND pto.object_id = $1 AND ptm.user_id = $2",
        event_id,
        reader_id,
    )

    assert tag_member["permission"] == "read"
    assert await permission_service.check_access("history", event_id, reader_id)


@pytest.mark.asyncio
async def test_page_inherits_folder_visibility_for_link_readers(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)
    inherited_page_id = await _make_page(
        pool, ws_id, owner_id, folder_id=folder_id, name="inherited"
    )
    private_page_id = await _make_page(pool, ws_id, owner_id, folder_id=folder_id, name="private")

    await permission_service.set_visibility("folder", folder_id, "link")
    await permission_service.set_visibility("page", private_page_id, "private")

    assert await permission_service.check_access("page", inherited_page_id, None)
    assert not await permission_service.check_access("page", private_page_id, None)


@pytest.mark.asyncio
async def test_page_inherits_folder_shares_for_authenticated_readers(pool):
    owner_id = await _make_user(pool)
    reader_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    folder_id = await _make_folder(pool, ws_id, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=folder_id)

    await permission_service.set_visibility("folder", folder_id, "private")
    await permission_service.add_share("folder", folder_id, reader_id, "read", owner_id)

    assert await permission_service.check_access("page", page_id, reader_id)


@pytest.mark.asyncio
async def test_private_folder_hides_inherited_pages_from_workspace_members(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    folder_id = await _make_folder(pool, ws_id, owner_id)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=folder_id)

    await permission_service.set_visibility("folder", folder_id, "private")

    assert not await permission_service.check_access("page", page_id, member_id)


@pytest.mark.asyncio
async def test_nested_folder_inherits_outer_folder_visibility(pool):
    """A nested folder's pages inherit visibility from the closest folder
    ancestor that has an explicit setting. A private outer folder hides
    everything beneath it even when the inner folder is left at 'inherit'."""
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'editor')",
        ws_id,
        member_id,
    )
    outer = await _make_folder(pool, ws_id, owner_id, name="outer")
    inner = await _make_folder(pool, ws_id, owner_id, name="inner", parent_folder_id=outer)
    page_id = await _make_page(pool, ws_id, owner_id, folder_id=inner)

    await permission_service.set_visibility("folder", outer, "private")

    assert not await permission_service.check_access("page", page_id, member_id)


@pytest.mark.asyncio
async def test_history_resolves_to_history_events_workspace(pool):
    owner_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    event_id = await pool.fetchval(
        "INSERT INTO history_events (workspace_id, created_by, agent_name, event_type, content) "
        "VALUES ($1, $2, 'agent', 'message', 'hello') RETURNING id",
        ws_id,
        owner_id,
    )

    assert await permission_service.resolve_workspace_id("history", event_id) == ws_id
