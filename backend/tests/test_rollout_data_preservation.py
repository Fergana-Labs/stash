import importlib
import os

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.services import embeddings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revision", ["0212_embedding_space_identity", "0218_session_curation_time"]
)
async def test_rollout_preserves_vectors_and_does_not_invent_historical_usage(
    pool, monkeypatch, revision
):
    migration = importlib.import_module(f"backend.migrations.versions.{revision}")
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        conn.execute(text("CREATE TEMP TABLE migration_test_scope (id int)"))
        conn.execute(text("SET LOCAL search_path TO pg_temp, public"))
        if revision.startswith("0212"):
            monkeypatch.setattr(embeddings, "space_id", lambda: "verified-existing-model")
            tables = [
                "pages",
                "table_rows",
                "history_events",
                "files",
                "granola_notes",
                "notion_index",
                "instagram_save_docs",
                "x_save_docs",
                "drive_documents",
                "slack_messages",
                "gong_documents",
                "github_documents",
            ]
            for table in tables:
                conn.execute(
                    text(f"CREATE TEMP TABLE {table} (embedding text, embed_stale boolean)")
                )
                conn.execute(text(f"INSERT INTO {table} VALUES ('original-vector', FALSE)"))
            conn.execute(text("CREATE TEMP TABLE embedding_projections (points text)"))
            conn.execute(text("INSERT INTO embedding_projections VALUES ('old layout')"))
        else:
            conn.execute(
                text(
                    "CREATE TEMP TABLE sessions (owner_user_id int, session_id text, last_event_at timestamptz, deleted_at timestamptz)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO sessions VALUES (1,'old-a','2020-01-01',NULL), (1,'old-b','2021-01-01',NULL)"
                )
            )
            conn.execute(
                text(
                    "CREATE TEMP TABLE agents (user_id int,is_curator boolean,curator_skill text,curated_through timestamptz)"
                )
            )
            conn.execute(text("INSERT INTO agents VALUES (1,TRUE,'internal','2026-09-01')"))
            conn.execute(
                text(
                    "CREATE TEMP TABLE history_events (owner_user_id int,session_id text,event_type text)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO history_events VALUES (1,'old-a','assistant_message'), (1,'old-b','assistant_message')"
                )
            )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        if revision.startswith("0212"):
            for table in tables:
                assert conn.execute(text(f"SELECT embedding,embed_stale FROM {table}")).one() == (
                    "original-vector",
                    False,
                )
            assert (
                conn.execute(text("SELECT space_id FROM embedding_space_state")).scalar_one()
                == "verified-existing-model"
            )
            assert (
                conn.execute(text("SELECT count(*) FROM embedding_projections")).scalar_one() == 0
            )
        else:
            assert (
                conn.execute(
                    text("SELECT count(*) FROM sessions WHERE curated_at IS NOT NULL")
                ).scalar_one()
                == 0
            )
            assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 2
            assert (
                conn.execute(
                    text("SELECT extract(year FROM curated_through) FROM agents")
                ).scalar_one()
                == 2026
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
