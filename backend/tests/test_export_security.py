import uuid

import pytest

from backend.exports.native.image_fetch import ImageFetcher
from backend.services import storage_service

from .conftest import unique_name


async def _make_user(pool):
    name = unique_name()
    row = await pool.fetchrow(
        "INSERT INTO users (name, display_name) VALUES ($1, $2) RETURNING id",
        name,
        name,
    )
    return row["id"]


async def _make_workspace(pool, creator_id):
    row = await pool.fetchrow(
        "INSERT INTO workspaces (name, creator_id, invite_code) VALUES ('ws', $1, $2) RETURNING id",
        creator_id,
        uuid.uuid4().hex[:12],
    )
    await pool.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
        row["id"],
        creator_id,
    )
    return row["id"]


async def _make_file(pool, workspace_id, uploaded_by):
    return await pool.fetchval(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, 'logo.png', 'image/png', 10, $2, $3) RETURNING id",
        workspace_id,
        f"test/{uuid.uuid4().hex}.png",
        uploaded_by,
    )


@pytest.mark.asyncio
async def test_image_fetcher_only_reads_authorized_stash_file(pool, monkeypatch):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    ws = await _make_workspace(pool, owner)
    file_id = await _make_file(pool, ws, owner)
    calls = []

    async def fake_download_file(storage_key):
        calls.append(storage_key)
        return b"image-bytes"

    monkeypatch.setattr(storage_service, "download_file", fake_download_file)
    src = f"/api/v1/workspaces/{ws}/files/{file_id}/download"

    assert await ImageFetcher(workspace_id=ws, user_id=owner).fetch(src) == b"image-bytes"
    assert await ImageFetcher(workspace_id=ws, user_id=stranger).fetch(src) is None
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_image_fetcher_rejects_cross_workspace_stash_file(pool, monkeypatch):
    first_owner = await _make_user(pool)
    second_owner = await _make_user(pool)
    first_ws = await _make_workspace(pool, first_owner)
    second_ws = await _make_workspace(pool, second_owner)
    file_id = await _make_file(pool, second_ws, second_owner)
    calls = []

    async def fake_download_file(storage_key):
        calls.append(storage_key)
        return b"image-bytes"

    monkeypatch.setattr(storage_service, "download_file", fake_download_file)
    src = f"/api/v1/workspaces/{second_ws}/files/{file_id}/download"

    assert await ImageFetcher(workspace_id=first_ws, user_id=first_owner).fetch(src) is None
    assert calls == []


@pytest.mark.asyncio
async def test_image_fetcher_rejects_remote_http_urls():
    assert await ImageFetcher().fetch("https://example.com/image.png") is None
