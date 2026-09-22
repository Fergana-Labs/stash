"""Already opted-out workspaces must lose access to knowledge compiled before enforcement."""

import importlib
import os
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.services import end_user_service, permission_service, shared_skill_service

from .test_developer_platform import _developer, _event, _mint_workspace_key, _push
from .test_permissions import _auth, _register_with_email


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["migration", "setting"])
async def test_existing_optout_archives_shared_tree_and_revokes_every_share(client, pool, method):
    api_key, _, workspace = await _developer(client)
    key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, key, [_event("s", "protected", "Protected customer")])
    owner = UUID(workspace["scope_user_id"])
    old_root = UUID(workspace["external_skill_folder_id"])
    protected = await pool.fetchval(
        "SELECT id FROM end_users WHERE workspace_id=$1", UUID(workspace["id"])
    )
    child = await pool.fetchval(
        "INSERT INTO folders (owner_user_id,created_by,name,parent_folder_id,public_permission) "
        "VALUES ($1,$1,'Compiled profiles',$2,'read') RETURNING id",
        owner,
        old_root,
    )
    page = await pool.fetchval(
        "INSERT INTO pages (owner_user_id,created_by,folder_id,name,content_markdown,public_permission) "
        "VALUES ($1,$1,$2,'Profile','PRE_ENFORCEMENT_SECRET','read') RETURNING id",
        owner,
        child,
    )
    table = await pool.fetchval(
        "INSERT INTO tables (owner_user_id,created_by,folder_id,name,public_permission) "
        "VALUES ($1,$1,$2,'Derived records','read') RETURNING id",
        owner,
        child,
    )
    file = await pool.fetchval(
        "INSERT INTO files (owner_user_id,uploaded_by,folder_id,end_user_id,name,content_type,size_bytes,storage_key,extracted_text,public_permission) "
        "VALUES ($1,$1,$2,$3,'PRE_ENFORCEMENT_SECRET','text/plain',10,'archive-test','PRE_ENFORCEMENT_SECRET','read') RETURNING id",
        owner,
        child,
        protected,
    )
    skill = await shared_skill_service.publish_folder(
        owner, owner, child, title="Compiled profiles", description="Published before revocation."
    )
    stranger_key, stranger = await _register_with_email(client, "stranger@example.com")
    await pool.execute(
        "INSERT INTO shares (owner_user_id,created_by,object_type,object_id,principal_type,principal_id,permission) "
        "VALUES ($1,$1,'page',$2,'user',$3,'read')",
        owner,
        page,
        UUID(stranger["id"]),
    )
    _, _, unaffected = await _developer(client)
    migration = importlib.import_module(
        "backend.migrations.versions.0204_curation_permission_generation"
    )
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        # Simulate the pre-deployment schema; upgrade must add the column itself.
        conn.execute(text("ALTER TABLE workspaces DROP COLUMN curation_generation"))
        renamed = [
            ("workspaces", "external_skill_folder_id", "external_wiki_folder_id"),
            ("end_users", "share_skill", "share_wiki"),
            ("agents", "curator_skill", "curator_wiki"),
        ]
        for table, current, historical in renamed:
            conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN {current} TO {historical}"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        for table, current, historical in renamed:
            conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN {historical} TO {current}"))

    try:
        if method == "migration":
            await pool.execute("UPDATE end_users SET share_skill=false WHERE id=$1", protected)
            async with engine.begin() as conn:
                await conn.run_sync(migrate)
        else:
            await end_user_service.update_end_user(protected, share_skill=False)
    finally:
        await engine.dispose()

    ws = await pool.fetchrow("SELECT * FROM workspaces WHERE id=$1", UUID(workspace["id"]))
    assert ws["external_skill_folder_id"] is not None and ws["external_skill_folder_id"] != old_root
    assert ws["curation_generation"] == 1
    assert await pool.fetchval(
        "SELECT external_skill_folder_id FROM workspaces WHERE id=$1", UUID(unaffected["id"])
    ) == UUID(unaffected["external_skill_folder_id"])
    assert (
        await pool.fetchval("SELECT content_markdown FROM pages WHERE id=$1", page)
        == "PRE_ENFORCEMENT_SECRET"
    )
    assert await pool.fetchval("SELECT public_permission FROM folders WHERE id=$1", child) == "none"
    assert await pool.fetchval("SELECT count(*) FROM shares WHERE object_id=$1", page) == 0
    assert (
        await pool.fetchval("SELECT count(*) FROM skills WHERE id=$1", UUID(str(skill["id"]))) == 0
    )
    assert await pool.fetchval("SELECT end_user_id FROM files WHERE id=$1", file) is None
    for kind, object_id in (("page", page), ("table", table), ("file", file)):
        assert not await permission_service.check_access(kind, object_id, None, owner)
    assert (
        await pool.fetchval(
            "SELECT curated_through FROM agents WHERE user_id=$1 AND curator_skill='external'",
            owner,
        )
        is None
    )
    for user in (None, "protected", "new-customer"):
        response = await client.post(
            "/api/v1/me/vfs",
            headers=_auth(key),
            json={"script": "grep -r PRE_ENFORCEMENT_SECRET /skills /files", "user_id": user},
        )
        assert response.status_code == 200
        assert "PRE_ENFORCEMENT_SECRET" not in response.json()["stdout"]
    for headers in ({}, _auth(stranger_key)):
        assert (await client.get(f"/api/v1/pages/{page}", headers=headers)).status_code == 404
    owner_read = await client.get(
        f"/api/v1/me/pages/{page}", headers={**_auth(api_key), "X-Stash-Scope": str(owner)}
    )
    assert owner_read.status_code == 200 and "PRE_ENFORCEMENT_SECRET" in owner_read.text
