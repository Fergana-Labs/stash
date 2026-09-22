"""Known internal-job duplicates disappear without hiding real user conversations."""

import importlib
import os
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.services import session_service

from .test_folder_skills import _auth, _register


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
        remaining = conn.execute(
            text("SELECT owner_user_id,session_id FROM sessions ORDER BY owner_user_id,session_id")
        ).all()
        assert remaining == [(1, "real-user-session"), (2, native)]
        assert conn.execute(text("SELECT session_id FROM history_events")).scalar_one() == job

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_already_trashed_duplicates_cannot_be_restored(client, pool):
    key, user = await _register(client)
    owner = uuid.UUID(user["id"])
    other_key, other_user = await _register(client)
    other = uuid.UUID(other_user["id"])
    job = "agent-curate-trash-regression"
    native = str(uuid.uuid5(uuid.NAMESPACE_URL, f"stash-agent:{job}"))
    await pool.execute(
        "INSERT INTO history_events (owner_user_id, session_id, agent_name, event_type, content) "
        "VALUES ($1, $2, 'Skills curator', 'message', 'Canonical audit log')",
        owner,
        job,
    )
    duplicate = await session_service.upsert_session(owner, native)
    unrelated = await session_service.upsert_session(owner, "real-user-session")
    other_duplicate = await session_service.upsert_session(other, native)
    for session, scope in [(duplicate, owner), (unrelated, owner), (other_duplicate, other)]:
        await session_service.delete_session(session["id"], scope, scope)

    migration = importlib.import_module(
        "backend.migrations.versions.0229_remove_trashed_curator_duplicates"
    )
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()

    trash = await client.get("/api/v1/me/trash", headers=_auth(key))
    assert trash.status_code == 200, trash.text
    assert [item["id"] for item in trash.json()["sessions"]] == [str(unrelated["id"])]
    response = await client.post(
        f"/api/v1/me/sessions/{duplicate['id']}/restore", headers=_auth(key)
    )
    assert response.status_code == 404, response.text
    assert await session_service.get_session(owner, native) is None
    for session, auth_key in [(unrelated, key), (other_duplicate, other_key)]:
        response = await client.post(
            f"/api/v1/me/sessions/{session['id']}/restore", headers=_auth(auth_key)
        )
        assert response.status_code == 204, response.text
    assert (
        await pool.fetchval(
            "SELECT content FROM history_events WHERE owner_user_id=$1 AND session_id=$2",
            owner,
            job,
        )
        == "Canonical audit log"
    )
