"""Deleting a folder must delete its subtree, not strand contents at the root.

The FKs on pages/files/tables are ON DELETE SET NULL, so before the service
swept the subtree, "delete folder" silently dumped every contained page, file,
and table at the scope root as live orphans (found in prod on 2026-07-10).
These tests pin the contract: contents get the same treatment their own delete
endpoints give them — pages/files to trash, tables hard-deleted.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import files_tree_service, table_service


@pytest_asyncio.fixture
async def scope(_db_pool):
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    return user_id, user_id


async def _make_file(pool, scope_id, user_id, folder_id):
    fid = uuid4()
    await pool.execute(
        "INSERT INTO files (id, owner_user_id, name, content_type, size_bytes, storage_key, "
        "uploaded_by, folder_id) VALUES ($1, $2, $3, 'text/plain', 1, $4, $5, $6)",
        fid,
        scope_id,
        f"f_{fid.hex[:6]}",
        f"key_{fid.hex[:6]}",
        user_id,
        folder_id,
    )
    return fid


@pytest.mark.asyncio
async def test_delete_folder_sweeps_subtree_instead_of_orphaning(scope, _db_pool):
    scope_id, user_id = scope
    root = await files_tree_service.create_folder(scope_id, "Project", user_id)
    sub = await files_tree_service.create_folder(
        scope_id, "Sub", user_id, parent_folder_id=root["id"]
    )
    top_page = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Top", created_by=user_id, folder_id=root["id"], content="t"
    )
    nested_page = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Nested", created_by=user_id, folder_id=sub["id"], content="n"
    )
    file_id = await _make_file(_db_pool, scope_id, user_id, sub["id"])
    table = await table_service.create_table(
        scope_id, "Data", "", [{"name": "Col", "type": "text"}], user_id, folder_id=root["id"]
    )

    assert await files_tree_service.delete_folder(root["id"], scope_id, user_id) is True

    # Both folders are gone.
    folders_left = await _db_pool.fetchval(
        "SELECT count(*) FROM folders WHERE id = ANY($1::uuid[])", [root["id"], sub["id"]]
    )
    assert folders_left == 0

    # Pages and the file are in trash, stamped with who deleted them — the
    # pre-fix bug left them live (deleted_at NULL) at the scope root.
    for page_id in (top_page["id"], nested_page["id"]):
        row = await _db_pool.fetchrow(
            "SELECT deleted_at, deleted_by FROM pages WHERE id = $1", page_id
        )
        assert row["deleted_at"] is not None
        assert row["deleted_by"] == user_id
    file_row = await _db_pool.fetchrow(
        "SELECT deleted_at, deleted_by FROM files WHERE id = $1", file_id
    )
    assert file_row["deleted_at"] is not None
    assert file_row["deleted_by"] == user_id

    # Tables have no trash; the row is gone.
    assert await _db_pool.fetchval("SELECT count(*) FROM tables WHERE id = $1", table["id"]) == 0

    # Nothing from the subtree is sitting live at the scope root.
    live_orphans = await _db_pool.fetchval(
        "SELECT count(*) FROM pages WHERE owner_user_id = $1 "
        "AND folder_id IS NULL AND deleted_at IS NULL",
        scope_id,
    )
    assert live_orphans == 0


@pytest.mark.asyncio
async def test_delete_folder_missing_or_foreign_returns_false(scope, _db_pool):
    scope_id, user_id = scope
    assert await files_tree_service.delete_folder(uuid4(), scope_id, user_id) is False

    # Another scope's folder is invisible to this scope's delete.
    other_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        other_id,
        f"u_{other_id.hex[:6]}",
    )
    theirs = await files_tree_service.create_folder(other_id, "Theirs", other_id)
    assert await files_tree_service.delete_folder(theirs["id"], scope_id, user_id) is False
    assert await _db_pool.fetchval("SELECT count(*) FROM folders WHERE id = $1", theirs["id"]) == 1


@pytest.mark.asyncio
async def test_delete_folder_still_refuses_memory(scope, _db_pool):
    scope_id, user_id = scope
    memory = await files_tree_service.get_or_create_memory_folder(scope_id, user_id)
    with pytest.raises(ValueError):
        await files_tree_service.delete_folder(memory["id"], scope_id, user_id)


@pytest.mark.asyncio
async def test_deleting_two_skill_folders_back_to_back(scope, _db_pool):
    """Each skill folder trashes a SKILL.md to the scope root on delete. With
    uniqueness enforced over trash too, the second delete blew up on the root
    name index (prod, 2026-08-06) — trash must accept repeated names."""
    scope_id, user_id = scope
    for _ in range(2):
        folder = await files_tree_service.create_skill(
            scope_id, user_id, "New skill", "Use this skill for deletion tests."
        )
        assert await files_tree_service.delete_folder(folder["id"], scope_id, user_id) is True

    trashed = await _db_pool.fetchval(
        "SELECT count(*) FROM pages WHERE owner_user_id = $1 AND name = 'SKILL.md' "
        "AND folder_id IS NULL AND deleted_at IS NOT NULL",
        scope_id,
    )
    assert trashed == 2


@pytest.mark.asyncio
async def test_restore_uniquifies_when_the_name_was_retaken(scope, _db_pool):
    """Trash no longer holds names, so a live page may take a trashed page's
    name. Restore must land on the next free name, not die on the index."""
    scope_id, user_id = scope
    old = await files_tree_service.create_page(
        owner_user_id=scope_id, name="Doc", created_by=user_id, content="v1"
    )
    assert await files_tree_service.delete_page(old["id"], scope_id, user_id) is True
    await files_tree_service.create_page(
        owner_user_id=scope_id, name="Doc", created_by=user_id, content="v2"
    )

    assert await files_tree_service.restore_page(old["id"], scope_id, user_id) is True

    restored = await _db_pool.fetchrow(
        "SELECT name, deleted_at FROM pages WHERE id = $1", old["id"]
    )
    assert restored["deleted_at"] is None
    assert restored["name"] == "Doc (2)"
