"""The rename changes the entry point, never the scope or stored knowledge."""

import importlib
import os

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_migration_preserves_ids_content_and_privacy(pool):
    migration = importlib.import_module("backend.migrations.versions.0223_wikis_become_skills")
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        conn.execute(text("CREATE TEMP TABLE migration_test_scope (id int)"))
        conn.execute(text("SET LOCAL search_path TO pg_temp, public"))
        statements = [
            "CREATE TEMP TABLE folders (id int PRIMARY KEY,owner_user_id int,name text,parent_folder_id int,is_memory boolean DEFAULT false,is_skill boolean DEFAULT false,agent_enabled boolean DEFAULT true,is_protected boolean DEFAULT true,skill_created_at timestamptz,created_at timestamptz DEFAULT now(),public_permission text DEFAULT 'none',CONSTRAINT folders_protected_is_never_a_skill CHECK (NOT(is_skill AND is_protected)))",
            "CREATE UNIQUE INDEX idx_folders_one_memory_per_owner ON folders(owner_user_id) WHERE is_memory",
            "CREATE TEMP TABLE users (id int, email text)",
            "CREATE TEMP TABLE workspaces (external_wiki_folder_id int,end_user_wikis_folder_id int,scope_user_id int,created_by int,domain text)",
            "CREATE TEMP TABLE end_users (id int,wiki_folder_id int,share_wiki boolean)",
            "CREATE TEMP TABLE agents (user_id int,curator_wiki text,is_curator boolean,name text)",
            "CREATE UNIQUE INDEX one_curator_per_user_per_wiki ON agents(user_id,curator_wiki) WHERE is_curator",
            "CREATE TEMP TABLE pages (id serial PRIMARY KEY,owner_user_id int,folder_id int,end_user_id int,name text,content_type text DEFAULT 'markdown',content_markdown text,content_html text,content_hash text,created_by int,updated_by int,deleted_at timestamptz,embed_stale boolean DEFAULT false,public_permission text DEFAULT 'none')",
            "INSERT INTO folders(id,owner_user_id,name,is_memory) VALUES (1,1,'Memory',true),(2,1,'Projects',false),(3,2,'External Wiki',false),(4,2,'customer-a',false),(5,2,'User Wikis',false),(6,3,'Shared wiki archive (6)',false)",
            "UPDATE folders SET parent_folder_id=1 WHERE id=2",
            "INSERT INTO workspaces VALUES (3,5,2,NULL,NULL),(10,12,10,11,NULL)",
            "INSERT INTO users VALUES (11,'stash@heaviai.com')",
            "INSERT INTO folders(id,owner_user_id,name,is_memory) VALUES (10,10,'External Wiki',false),(12,10,'User Wikis',false),(13,10,'Memory',true)",
            "INSERT INTO end_users VALUES (7,4,false)",
            "INSERT INTO agents VALUES (1,'internal',true,'Memory curator'),(2,'external',true,'External wiki curator')",
        ]
        for statement in statements:
            conn.execute(text(statement))
        index = "# Memory Wiki\n\n[Project](/p/original-page-id)\n"
        reference = "The customer-specific decision and its original citation.\n"
        existing_skill = (
            '---\nname: "Private"\ndescription: "Only customer A"\n---\n\nPrivate facts.\n'
        )
        for folder, name, body in [
            (1, "Memory Wiki", index),
            (2, "Project", reference),
            (4, "SKILL.md", existing_skill),
            (6, "SKILL.md", ""),
        ]:
            conn.execute(
                text(
                    "INSERT INTO pages(owner_user_id,folder_id,name,content_markdown) VALUES (1,:folder,:name,:body)"
                ),
                {"folder": folder, "name": name, "body": body},
            )
        conn.execute(
            text(
                "UPDATE pages SET content_type='html',content_html='<h1>Archived knowledge</h1>' WHERE folder_id=6"
            )
        )
        conn.execute(
            text(
                "INSERT INTO pages(owner_user_id,folder_id,name,content_markdown) VALUES (10,10,'Memory Wiki','Original Heavi index')"
            )
        )
        original_ids = conn.execute(text("SELECT id FROM pages ORDER BY id")).scalars().all()
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        pages = (
            conn.execute(
                text(
                    "SELECT id,name,content_markdown,content_html,public_permission FROM pages ORDER BY id"
                )
            )
            .mappings()
            .all()
        )
        assert [p["id"] for p in pages[:5]] == original_ids
        assert pages[4]["name"] == "Memory Wiki"
        assert pages[4]["content_markdown"] == "Original Heavi index"
        assert not conn.execute(text("SELECT is_skill FROM folders WHERE id=10")).scalar_one()
        assert (
            conn.execute(text("SELECT name FROM folders WHERE id=12")).scalar_one() == "User Wikis"
        )
        rollout = importlib.import_module("backend.migrations.versions.0225_heavi_wiki_contract")
        with Operations.context(MigrationContext.configure(conn)):
            rollout.upgrade()
        assert conn.execute(
            text("SELECT legacy_wiki_enabled FROM workspaces WHERE scope_user_id=10")
        ).scalar_one()
        assert not conn.execute(
            text("SELECT legacy_wiki_enabled FROM workspaces WHERE scope_user_id=2")
        ).scalar_one()
        assert pages[0]["name"] == "SKILL.md"
        assert pages[0]["content_markdown"].endswith(index)
        assert pages[1]["content_markdown"] == reference
        assert pages[2]["content_markdown"].endswith(existing_skill)
        assert pages[3]["name"].startswith("Original Skill index (")
        assert pages[3]["content_html"] == "<h1>Archived knowledge</h1>"
        assert not conn.execute(text("SELECT agent_enabled FROM folders WHERE id=6")).scalar_one()
        assert all(p["public_permission"] == "none" for p in pages)
        assert conn.execute(
            text("SELECT id FROM folders WHERE is_skill ORDER BY id")
        ).scalars().all() == [1, 3, 4, 6]
        assert (
            conn.execute(text("SELECT parent_folder_id FROM folders WHERE id=2")).scalar_one() == 1
        )
        assert conn.execute(text("SELECT skill_folder_id,share_skill FROM end_users")).one() == (
            4,
            False,
        )
        assert conn.execute(
            text(
                "SELECT external_skill_folder_id,end_user_skills_folder_id FROM workspaces WHERE scope_user_id=2"
            )
        ).one() == (3, 5)
        assert (
            conn.execute(text("SELECT curator_skill FROM agents WHERE user_id=1")).scalar_one()
            == "internal"
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM pages WHERE folder_id=3 AND name='SKILL.md'")
            ).scalar_one()
            == 1
        )

    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                await conn.run_sync(migrate)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
