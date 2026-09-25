"""Older ordinary Skills must survive the strict catalog rollout."""

import hashlib
import importlib
import os
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import create_async_engine

from backend.services import files_tree_service, shared_skill_service, skill_service

from .test_folder_skills import _auth, _register


async def _migrate():
    migration = importlib.import_module("backend.migrations.versions.0228_repair_existing_skills")
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    "legacy_content",
    [
        None,
        "",
        "# Existing instructions\n\nKeep every word.\n",
        '---\nname: "   "\ndescription: "  "\nwhen_to_use: Always\n---\n\nOriginal body.\n',
        "---\nname: Existing name\n---\n\nOriginal body.\n",
        "---\ndescription: Existing description\n---\n\nOriginal body.\n",
        f"---\nname: {'n' * 65}\ndescription: {'d' * 1025}\n---\n\nOriginal body.\n",
    ],
    ids=[
        "missing",
        "empty",
        "no-frontmatter",
        "blank-metadata",
        "missing-description",
        "missing-name",
        "too-long",
    ],
)
async def test_migration_repairs_ordinary_skills_without_losing_data(
    client, pool, enabled, legacy_content
):
    key, user = await _register(client)
    owner = UUID(user["id"])
    healthy = await files_tree_service.create_skill(owner, owner, "Healthy", "Already valid.", "")
    healthy_before = await pool.fetchrow("SELECT * FROM pages WHERE folder_id=$1", healthy["id"])
    folder = await files_tree_service.create_skill(
        owner, owner, "Older Skill", "Old description.", ""
    )
    published = await shared_skill_service.publish_folder(
        owner, owner, folder["id"], title="Public title", description="Published description."
    )
    await pool.execute("UPDATE folders SET agent_enabled=$2 WHERE id=$1", folder["id"], enabled)
    page = await pool.fetchrow("SELECT * FROM pages WHERE folder_id=$1", folder["id"])
    if legacy_content is None:
        await pool.execute("DELETE FROM pages WHERE id=$1", page["id"])
    else:
        await pool.execute(
            "UPDATE pages SET content_markdown=$2, embed_stale=false WHERE id=$1",
            page["id"],
            legacy_content,
        )
    folder_before = await pool.fetchrow("SELECT * FROM folders WHERE id=$1", folder["id"])
    publish_before = await pool.fetchrow("SELECT * FROM skills WHERE id=$1", published["id"])
    nested = await files_tree_service.create_folder(owner, "References", owner, folder["id"])
    supporting = await files_tree_service.create_page(
        owner, "Notes", owner, folder_id=nested["id"], content="Keep this supporting knowledge."
    )
    support_before = await pool.fetchrow("SELECT * FROM pages WHERE id=$1", supporting["id"])
    # Unflagged folders are ordinary files, even when a page is named SKILL.md.
    ordinary = await files_tree_service.create_folder(owner, "Not a Skill", owner)
    ordinary_page = await files_tree_service.create_page(
        owner, "SKILL.md", owner, folder_id=ordinary["id"], content="Ordinary notes."
    )
    ordinary_before = await pool.fetchrow("SELECT * FROM pages WHERE id=$1", ordinary_page["id"])

    await _migrate()

    repaired = await pool.fetchrow("SELECT * FROM pages WHERE folder_id=$1", folder["id"])
    skill_service.validate_skill_md(repaired["content_markdown"])
    metadata, body = skill_service.parse_frontmatter(repaired["content_markdown"])
    if legacy_content is not None:
        assert repaired["id"] == page["id"]
        assert body == skill_service.parse_frontmatter(legacy_content)[1]
    if "name:" not in (legacy_content or "") or 'name: "   "' in legacy_content:
        assert metadata["name"] == "Older Skill"
    if "description:" not in (legacy_content or "") or 'description: "  "' in legacy_content:
        assert metadata["description"] == "Published description."
    if "when_to_use:" in (legacy_content or ""):
        assert metadata["when_to_use"] == "Always"
    assert (
        repaired["content_hash"]
        == hashlib.sha256(repaired["content_markdown"].encode()).hexdigest()
    )
    assert repaired["embed_stale"] is True
    assert await pool.fetchrow("SELECT * FROM folders WHERE id=$1", folder["id"]) == folder_before
    assert (
        await pool.fetchrow("SELECT * FROM skills WHERE id=$1", published["id"]) == publish_before
    )
    assert (
        await pool.fetchrow("SELECT * FROM pages WHERE id=$1", supporting["id"]) == support_before
    )
    assert (
        await pool.fetchrow("SELECT * FROM pages WHERE id=$1", ordinary_page["id"])
        == ordinary_before
    )
    assert (
        await pool.fetchrow("SELECT * FROM pages WHERE folder_id=$1", healthy["id"])
        == healthy_before
    )

    for include_disabled in (False, True):
        response = await client.get(
            "/api/v1/me/skills", params={"include_disabled": include_disabled}, headers=_auth(key)
        )
        assert response.status_code == 200, response.text
        ids = {skill["folder_id"] for skill in response.json()["skills"]}
        assert str(healthy["id"]) in ids
        assert (str(folder["id"]) in ids) == (enabled or include_disabled)

    await _migrate()
    assert await pool.fetchrow("SELECT * FROM pages WHERE folder_id=$1", folder["id"]) == repaired


@pytest.mark.asyncio
async def test_missing_entry_is_created_without_restoring_deleted_instructions(client, pool):
    key, user = await _register(client)
    owner = UUID(user["id"])
    folder = await files_tree_service.create_skill(
        owner, owner, "Older Skill", "Old description.", ""
    )
    await pool.execute("UPDATE pages SET deleted_at=now() WHERE folder_id=$1", folder["id"])
    deleted = await pool.fetchrow("SELECT * FROM pages WHERE folder_id=$1", folder["id"])

    await _migrate()

    assert await pool.fetchrow("SELECT * FROM pages WHERE id=$1", deleted["id"]) == deleted
    entry = await pool.fetchrow(
        "SELECT * FROM pages WHERE folder_id=$1 AND deleted_at IS NULL", folder["id"]
    )
    assert entry["id"] != deleted["id"]
    metadata, body = skill_service.parse_frontmatter(entry["content_markdown"])
    assert metadata == {
        "name": "Older Skill",
        "description": "Use this skill for tasks related to Older Skill.",
    }
    assert body == ""
    assert (await client.get("/api/v1/me/skills", headers=_auth(key))).status_code == 200
