"""Private audit history must survive migration without remaining in customer memory."""

import hashlib
import importlib
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from .test_developer_platform import _developer, _event, _mint_workspace_key, _push
from .test_permissions import _auth, _register_with_email


@pytest.mark.asyncio
async def test_archive_preserves_logs_and_removes_customer_access(client, pool):
    api_key, _, workspace = await _developer(client)
    key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, key, [_event("shop-session", user_id="shop", user_name="Shop")])
    owner = uuid.UUID(workspace["scope_user_id"])
    root = uuid.UUID(workspace["external_wiki_folder_id"])
    system = await pool.fetchval(
        "INSERT INTO folders (owner_user_id, created_by, name, parent_folder_id) "
        "VALUES ($1, $1, '_system', $2) RETURNING id",
        owner,
        root,
    )

    async def page(name, folder, content):
        return await pool.fetchval(
            "INSERT INTO pages (owner_user_id, created_by, name, folder_id, content_markdown) "
            "VALUES ($1, $1, $2, $3, $4) RETURNING id",
            owner,
            name,
            folder,
            content,
        )

    private_text = "Removed VIN PRIVATEVIN12345678 from a customer's notes."
    current = await page("Log", root, private_text)
    old = await page("changelog", system, "Old private audit history")
    trashed = await page("Log", system, "Deleted audit history must restore privately")
    await pool.execute("UPDATE pages SET deleted_at = now() WHERE id = $1", trashed)
    internal = await page("Log", None, "Developer's unrelated log")
    topic = await page("Brake Shoes", root, "Confirm axle position before choosing a kit.")
    index = await page(
        "Wiki Index",
        root,
        f"# Wiki Index\n- [Log](/p/{current})\n- [Old log](/p/{old})\n"
        "- Read `/memory/_system/changelog.md` for audit history.\n"
        f"- [Brake Shoes](/p/{topic})\n",
    )
    stranger_key, stranger = await _register_with_email(client, "archive-reader@example.com")
    await pool.execute("UPDATE pages SET public_permission = 'read' WHERE id = $1", current)
    await pool.execute(
        "INSERT INTO shares (owner_user_id, created_by, object_type, object_id, "
        "principal_type, principal_id, permission) VALUES ($1, $1, 'page', $2, 'user', $3, 'read')",
        owner,
        current,
        uuid.UUID(stranger["id"]),
    )

    migration = importlib.import_module(
        "backend.migrations.versions.0203_archive_external_curator_logs"
    )
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()

    archived = await pool.fetchrow("SELECT * FROM pages WHERE id = $1", current)
    archive = await pool.fetchrow("SELECT * FROM folders WHERE id = $1", archived["folder_id"])
    assert archive["parent_folder_id"] is None
    assert archive["public_permission"] == "none"
    assert archived["content_markdown"] == private_text
    assert archived["public_permission"] == "none"
    assert archived["end_user_id"] is None
    assert await pool.fetchval("SELECT folder_id FROM pages WHERE id = $1", old) == archive["id"]
    assert (
        await pool.fetchval("SELECT folder_id FROM pages WHERE id = $1", trashed) == archive["id"]
    )
    assert await pool.fetchval("SELECT folder_id FROM pages WHERE id = $1", internal) is None
    assert await pool.fetchval("SELECT count(*) FROM shares WHERE object_id = $1", current) == 0
    cleaned = await pool.fetchrow("SELECT * FROM pages WHERE id = $1", index)
    assert cleaned["content_markdown"] == f"# Wiki Index\n- [Brake Shoes](/p/{topic})\n"
    assert (
        cleaned["content_hash"] == hashlib.sha256(cleaned["content_markdown"].encode()).hexdigest()
    )
    assert cleaned["embed_stale"] is True

    for user in (None, "shop", "new-shop"):
        for script in (
            "find / -type f",
            "grep -r 'PRIVATEVIN12345678' /memory /files",
            "cat /memory/Log.md",
            "cat /memory/_system/changelog.md",
            f"cat '/files/Curator log archive/{archived['name']}.md'",
        ):
            response = await client.post(
                "/api/v1/me/vfs",
                json={"script": script, "user_id": user},
                headers=_auth(key),
            )
            assert response.status_code == 200, response.text
            assert "PRIVATEVIN12345678" not in response.json()["stdout"]
            if script.startswith("cat"):
                assert response.json()["exit_code"] != 0
            if script.startswith("find"):
                assert "Brake Shoes" in response.json()["stdout"]
                assert "Log.md" not in response.json()["stdout"]
                assert "Curator log archive" not in response.json()["stdout"]

    # The old public link and explicit share no longer grant access. The
    # developer's workspace credential still retains its intended owner access.
    for headers in ({}, _auth(stranger_key)):
        response = await client.get(f"/api/v1/pages/{current}", headers=headers)
        assert response.status_code == 404
    response = await client.get(
        f"/api/v1/me/pages/{current}",
        headers={**_auth(api_key), "X-Stash-Scope": str(owner)},
    )
    assert response.status_code == 200, response.text
    assert private_text in response.text
