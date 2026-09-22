"""Known internal-job duplicates disappear without hiding real user conversations."""

import importlib
import os
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_cleanup_matches_job_identity_and_owner(pool):
    migration = importlib.import_module(
        "backend.migrations.versions.0226_hide_reuploaded_curator_runs"
    )
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        conn.execute(text("CREATE TEMP TABLE history_events (owner_user_id int, session_id text)"))
        conn.execute(
            text(
                "CREATE TEMP TABLE sessions (owner_user_id int, session_id text, deleted_at timestamptz)"
            )
        )
        conn.execute(text("SET LOCAL search_path TO pg_temp, public"))
        job = "agent-curate-test-20260922"
        native = str(uuid.uuid5(uuid.NAMESPACE_URL, f"stash-agent:{job}"))
        conn.execute(text("INSERT INTO history_events VALUES (1,:job)"), {"job": job})
        for owner, session in [(1, native), (2, native), (1, "real-user-session")]:
            conn.execute(
                text("INSERT INTO sessions VALUES (:owner,:session,NULL)"),
                {"owner": owner, "session": session},
            )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()
        hidden = conn.execute(
            text("SELECT owner_user_id,session_id FROM sessions WHERE deleted_at IS NOT NULL")
        ).all()
        assert hidden == [(1, native)]
        assert conn.execute(text("SELECT session_id FROM history_events")).scalar_one() == job

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()
