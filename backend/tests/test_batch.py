"""Batch move/delete/restore — best-effort semantics: good items apply, bad
ones come back as per-item errors without blocking the rest."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from backend.services import batch_service, files_tree_service


@pytest_asyncio.fixture
async def scope(_db_pool):
    user_id = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        user_id,
        f"u_{user_id.hex[:6]}",
    )
    # The scope is the user: owner_user_id == user_id.
    return user_id, user_id


async def _make_file(pool, scope_id, user_id, folder_id=None):
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
async def test_batch_move_partial_success(scope, _db_pool):
    """A move where one item belongs to another scope: the good items move,
    the bad one comes back as an error — the batch isn't all-or-nothing."""
    scope_id, user_id = scope
    folder = await files_tree_service.create_folder(scope_id, "Dest", user_id)
    page = await files_tree_service.create_page(
        owner_user_id=scope_id, name="P", created_by=user_id
    )
    file_id = await _make_file(_db_pool, scope_id, user_id)
    stranger_page = uuid4()  # never inserted → not found

    result = await batch_service.batch_move(
        scope_id,
        user_id,
        [
            {"object_type": "page", "object_id": str(page["id"])},
            {"object_type": "file", "object_id": str(file_id)},
            {"object_type": "page", "object_id": str(stranger_page)},
        ],
        target_folder_id=folder["id"],
    )

    assert {s["object_id"] for s in result["succeeded"]} == {str(page["id"]), str(file_id)}
    assert [e["object_id"] for e in result["errors"]] == [str(stranger_page)]
    # The good items really landed in the folder.
    assert (
        await _db_pool.fetchval("SELECT folder_id FROM pages WHERE id = $1", page["id"])
    ) == folder["id"]
    assert (
        await _db_pool.fetchval("SELECT folder_id FROM files WHERE id = $1", file_id)
    ) == folder["id"]


@pytest.mark.asyncio
async def test_batch_delete_and_restore_pages_and_files(scope, _db_pool):
    scope_id, user_id = scope
    page = await files_tree_service.create_page(
        owner_user_id=scope_id, name="P2", created_by=user_id
    )
    file_id = await _make_file(_db_pool, scope_id, user_id)
    items = [
        {"object_type": "page", "object_id": str(page["id"])},
        {"object_type": "file", "object_id": str(file_id)},
    ]

    deleted = await batch_service.batch_delete(scope_id, user_id, items)
    assert len(deleted["succeeded"]) == 2 and not deleted["errors"]
    assert await _db_pool.fetchval("SELECT deleted_at FROM pages WHERE id = $1", page["id"])
    assert await _db_pool.fetchval("SELECT deleted_at FROM files WHERE id = $1", file_id)

    restored = await batch_service.batch_restore(scope_id, user_id, items)
    assert len(restored["succeeded"]) == 2 and not restored["errors"]
    assert await _db_pool.fetchval("SELECT deleted_at FROM pages WHERE id = $1", page["id"]) is None


@pytest.mark.asyncio
async def test_batch_delete_rejects_unsupported_type(scope, _db_pool):
    """Folders/tables hard-delete, so batch delete refuses them (fail loud per
    item) rather than silently wiping a subtree."""
    scope_id, user_id = scope
    folder = await files_tree_service.create_folder(scope_id, "Keep", user_id)
    result = await batch_service.batch_delete(
        scope_id, user_id, [{"object_type": "folder", "object_id": str(folder["id"])}]
    )
    assert not result["succeeded"]
    assert "folder" in result["errors"][0]["reason"]
    # Folder still there.
    assert await _db_pool.fetchval("SELECT 1 FROM folders WHERE id = $1", folder["id"])


@pytest.mark.asyncio
async def test_batch_move_rejects_cross_scope_item(scope, _db_pool):
    """An item in another scope must error, not move — even though the caller
    owns the request scope."""
    scope_id, user_id = scope
    other_scope = uuid4()
    await _db_pool.execute(
        "INSERT INTO users (id, name, display_name) VALUES ($1, $2, $2)",
        other_scope,
        f"u_{other_scope.hex[:6]}",
    )
    other_page = await files_tree_service.create_page(
        owner_user_id=other_scope, name="Other", created_by=user_id
    )
    result = await batch_service.batch_move(
        scope_id,
        user_id,
        [{"object_type": "page", "object_id": str(other_page["id"])}],
        move_to_root=True,
    )
    assert not result["succeeded"]
    assert result["errors"][0]["reason"] == "not found"
