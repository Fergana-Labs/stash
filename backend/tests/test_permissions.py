"""Tests for the permission service — visibility modes and write-access logic."""

import uuid

import pytest

from backend.services import permission_service
from .conftest import unique_name


async def _make_user(pool, name=None):
    name = name or unique_name()
    api_key_hash = "hash_" + uuid.uuid4().hex
    row = await pool.fetchrow(
        "INSERT INTO users (name, type, api_key_hash) VALUES ($1, 'human', $2) RETURNING id",
        name, api_key_hash,
    )
    return row["id"]


async def _make_workspace(pool, creator_id):
    invite = uuid.uuid4().hex[:12]
    row = await pool.fetchrow(
        "INSERT INTO workspaces (name, creator_id, invite_code) VALUES ('ws', $1, $2) RETURNING id",
        creator_id, invite,
    )
    ws_id = row["id"]
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
        ws_id, creator_id,
    )
    return ws_id


async def _make_notebook(pool, workspace_id, created_by):
    row = await pool.fetchrow(
        "INSERT INTO notebooks (workspace_id, name, created_by) VALUES ($1, 'nb', $2) RETURNING id",
        workspace_id, created_by,
    )
    return row["id"]


@pytest.mark.asyncio
async def test_owner_has_access(pool):
    user_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, user_id)
    nb_id = await _make_notebook(pool, ws_id, user_id)

    assert await permission_service.check_access("notebook", nb_id, user_id, workspace_id=ws_id)
    assert await permission_service.check_access("notebook", nb_id, user_id, workspace_id=ws_id, require_write=True)


@pytest.mark.asyncio
async def test_member_read_inherit(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'member')",
        ws_id, member_id,
    )
    nb_id = await _make_notebook(pool, ws_id, owner_id)

    # Member can read (inherit default)
    assert await permission_service.check_access("notebook", nb_id, member_id, workspace_id=ws_id)


@pytest.mark.asyncio
async def test_member_cannot_write_without_share(pool):
    """Regression test for the write-access logic hole that was fixed in Phase 1.4."""
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'member')",
        ws_id, member_id,
    )
    nb_id = await _make_notebook(pool, ws_id, owner_id)

    # Member must NOT have write access by default on inherit-visibility objects
    result = await permission_service.check_access(
        "notebook", nb_id, member_id, workspace_id=ws_id, require_write=True
    )
    assert not result


@pytest.mark.asyncio
async def test_member_can_write_with_share(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'member')",
        ws_id, member_id,
    )
    nb_id = await _make_notebook(pool, ws_id, owner_id)

    await permission_service.add_share("notebook", nb_id, member_id, "write", owner_id)
    result = await permission_service.check_access(
        "notebook", nb_id, member_id, workspace_id=ws_id, require_write=True
    )
    assert result


@pytest.mark.asyncio
async def test_non_member_denied(pool):
    owner_id = await _make_user(pool)
    stranger_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    nb_id = await _make_notebook(pool, ws_id, owner_id)

    assert not await permission_service.check_access("notebook", nb_id, stranger_id, workspace_id=ws_id)


@pytest.mark.asyncio
async def test_public_visibility_readable_by_anyone(pool):
    owner_id = await _make_user(pool)
    stranger_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    nb_id = await _make_notebook(pool, ws_id, owner_id)

    await permission_service.set_visibility("notebook", nb_id, "public")
    assert await permission_service.check_access("notebook", nb_id, stranger_id)


@pytest.mark.asyncio
async def test_private_visibility_denies_member(pool):
    owner_id = await _make_user(pool)
    member_id = await _make_user(pool)
    ws_id = await _make_workspace(pool, owner_id)
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'member')",
        ws_id, member_id,
    )
    nb_id = await _make_notebook(pool, ws_id, owner_id)

    await permission_service.set_visibility("notebook", nb_id, "private")
    assert not await permission_service.check_access("notebook", nb_id, member_id, workspace_id=ws_id)
