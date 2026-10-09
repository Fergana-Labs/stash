"""Exercise the Drive identity migration against legacy duplicate cache rows."""

import importlib
from uuid import UUID

import asyncpg
import pytest

from backend.services import source_service

from .conftest import unique_name


@pytest.mark.asyncio
async def test_drive_identity_migration_preserves_the_best_copy_and_distinct_files(
    client, pool, monkeypatch
):
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("identity"), "password": "securepassword1"},
    )
    owner_id = UUID(response.json()["id"])
    source = await source_service.create_source(
        owner_user_id=owner_id,
        source_type="google_drive_folder",
        external_ref="folder",
        display_name="Skills",
    )
    source_id = UUID(source["id"])
    migration = importlib.import_module("backend.migrations.versions.0228_drive_document_identity")
    statements = []
    monkeypatch.setattr(migration.op, "execute", statements.append)
    migration.downgrade()
    downgrade = statements[:]
    statements.clear()
    migration.upgrade()

    # Roll back all schema/data changes: the session's shared database stays at
    # head even if an assertion fails halfway through testing the old schema.
    async with pool.acquire() as conn:
        transaction = conn.transaction()
        await transaction.start()
        try:
            for statement in downgrade:
                await conn.execute(statement)
            for path, ref, date, content, deleted in (
                ("old path", "same-file", "2026-08-01", "old", False),
                ("new path", "same-file", "2026-09-01", "new", False),
                ("pending copy", "same-file", "2026-09-01", None, False),
                ("deleted copy", "same-file", "2026-10-01", "deleted", True),
                ("other file", "different-file", "2026-09-01", "separate", False),
            ):
                await conn.execute(
                    "INSERT INTO drive_documents "
                    "(source_id, owner_user_id, path, name, external_ref, external_updated_at, "
                    "content, deleted_at) VALUES ($1, $2, $3, 'same name', $4, $5::text::date, "
                    "$6, CASE WHEN $7 THEN now() ELSE NULL END)",
                    source_id,
                    owner_id,
                    path,
                    ref,
                    date,
                    content,
                    deleted,
                )
            for statement in statements:
                await conn.execute(statement)
            rows = await conn.fetch(
                "SELECT path, content FROM drive_documents WHERE source_id = $1 ORDER BY path",
                source_id,
            )
            assert [(row["path"], row["content"]) for row in rows] == [
                ("new path", "new"),
                ("other file", "separate"),
            ]
            with pytest.raises(asyncpg.UniqueViolationError):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO drive_documents (source_id, owner_user_id, path, name, external_ref) "
                        "VALUES ($1, $2, 'another path', 'same name', 'same-file')",
                        source_id,
                        owner_id,
                    )
            # Renames may temporarily overlap, but the final tree stays unique.
            await conn.execute("SET CONSTRAINTS drive_documents_source_id_path_key DEFERRED")
            await conn.execute(
                "UPDATE drive_documents SET path = 'other file' WHERE source_id = $1 "
                "AND external_ref = 'same-file'",
                source_id,
            )
            await conn.execute(
                "UPDATE drive_documents SET path = 'new path' WHERE source_id = $1 "
                "AND external_ref = 'different-file'",
                source_id,
            )
            await conn.execute("SET CONSTRAINTS drive_documents_source_id_path_key IMMEDIATE")
            for statement in downgrade:
                await conn.execute(statement)
        finally:
            await transaction.rollback()
