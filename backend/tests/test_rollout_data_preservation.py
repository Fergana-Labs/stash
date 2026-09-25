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


@pytest.mark.asyncio
async def test_token_rollout_grandfathers_only_already_curated_content(pool):
    migration = importlib.import_module("backend.migrations.versions.0224_transcript_token_usage")
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        conn.execute(text("CREATE SCHEMA token_rollout_test"))
        conn.execute(text("SET LOCAL search_path TO token_rollout_test, public"))
        statements = [
            "CREATE TABLE users (id uuid PRIMARY KEY)",
            "CREATE TABLE user_subscriptions (user_id uuid)",
            "CREATE TABLE sessions (owner_user_id uuid,session_id text,end_user_id uuid,curated_at timestamptz)",
            "CREATE TABLE agents (user_id uuid,is_curator boolean,curator_skill text,curated_through timestamptz)",
            "CREATE TABLE history_events (owner_user_id uuid,session_id text,event_type text,content text,created_at timestamptz)",
            "INSERT INTO users VALUES ('00000000-0000-0000-0000-000000000001')",
            "INSERT INTO user_subscriptions SELECT id FROM users",
            "INSERT INTO sessions SELECT id,'personal',NULL,NULL FROM users",
            "INSERT INTO sessions SELECT id,'external',id,NULL FROM users",
            "INSERT INTO agents SELECT id,true,'internal','2024-01-01' FROM users",
            "INSERT INTO agents SELECT id,true,'external','2026-01-01' FROM users",
            "INSERT INTO history_events SELECT id,'personal','assistant_message','already curated','2020-01-01' FROM users",
            "INSERT INTO history_events SELECT id,'personal','assistant_message','pending personal','2025-01-01' FROM users",
            "INSERT INTO history_events SELECT id,'external','assistant_message','already curated external','2025-01-01' FROM users",
            "INSERT INTO history_events SELECT id,'external','assistant_message','pending external','2027-01-01' FROM users",
        ]
        for statement in statements:
            conn.execute(text(statement))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert conn.execute(text("SELECT count(*),sum(tokens) FROM transcript_usage")).one() == (
            2,
            0,
        )
        assert conn.execute(text("SELECT count(*) FROM history_events")).scalar_one() == 4
        assert conn.execute(text("SELECT count(*) FROM transcript_meter_events")).scalar_one() == 0
        assert (
            conn.execute(text("SELECT overage_limit_cents FROM user_subscriptions")).scalar_one()
            == 0
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema='token_rollout_test' AND table_name='sessions' AND column_name='curated_at'"
                )
            ).scalar_one()
            == 0
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
