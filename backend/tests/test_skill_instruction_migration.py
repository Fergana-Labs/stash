import importlib
import json

import pytest

from backend.services import skill_service

migration = importlib.import_module("backend.migrations.versions.0208_skill_instruction_bodies")


@pytest.mark.parametrize("body", ["", "\n", "\n# Release: web\n"])
def test_title_only_skills_gain_instructions_without_losing_metadata(body):
    description = 'Deploy safely: verify "production".\nCheck the rollback plan.'
    original = (
        '---\nname: "Release: web"\n'
        f"description: {json.dumps(description)}\n"
        "when_to_use: production deploys\nmcp_exposed: true\n---\n" + body
    )
    updated = migration._with_instructions(original)
    assert updated.startswith(original)
    assert skill_service.skill_instruction_body(updated) == description
    skill_service.validate_skill_md(updated)
    assert migration._with_instructions(updated) == updated


def test_authored_instructions_remain_byte_for_byte_unchanged():
    original = (
        "---\nname: Deploy\ndescription: Ship safely.\nversion: 4\n---\n\n"
        "# Deploy\n\nRun tests, inspect the diff, and confirm the deploy.\n"
    )
    assert migration._with_instructions(original) == original


def test_invalid_metadata_stops_migration_instead_of_replacing_content():
    with pytest.raises(ValueError, match="valid frontmatter"):
        migration._with_instructions("Do not discard these instructions.")


@pytest.mark.asyncio
async def test_database_migration_preserves_files_and_only_updates_stubs(pool):
    import hashlib
    import os

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    stub = "---\nname: Deploy\ndescription: Ship safely.\nwhen_to_use: releases\n---\n# Deploy\n"
    authored = stub + "\nRun the full test suite first.\n"
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        conn.execute(text("CREATE TEMP TABLE folders (id int, is_skill boolean) ON COMMIT DROP"))
        conn.execute(
            text(
                "CREATE TEMP TABLE pages (id int, folder_id int, name text, "
                "content_markdown text, content_hash text, updated_at timestamptz, "
                "deleted_at timestamptz) ON COMMIT DROP"
            )
        )
        conn.execute(text("INSERT INTO folders VALUES (1, true), (2, false)"))
        for id, folder, name, content in [
            (1, 1, "SKILL.md", stub),
            (2, 1, "notes.md", "Keep these notes."),
            (3, 2, "SKILL.md", stub),
            (4, 1, "SKILL.md", authored),
        ]:
            conn.execute(
                text(
                    "INSERT INTO pages (id,folder_id,name,content_markdown,updated_at) "
                    "VALUES (:id,:folder,:name,:content,'2000-01-01')"
                ),
                dict(id=id, folder=folder, name=name, content=content),
            )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        rows = {r.id: r for r in conn.execute(text("SELECT * FROM pages"))}
        assert rows[1].content_markdown.startswith(stub)
        assert rows[1].content_hash == hashlib.sha256(rows[1].content_markdown.encode()).hexdigest()
        assert rows[1].updated_at.year > 2000
        assert rows[2].content_markdown == "Keep these notes."
        assert rows[3].content_markdown == stub
        assert rows[4].content_markdown == authored
        assert all(rows[id].updated_at.year == 2000 for id in (2, 3, 4))

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()
