"""The signup cohort is persisted, so returning users keep their product surface."""

import importlib
import os
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .conftest import unique_name


@pytest.mark.asyncio
async def test_migration_preserves_existing_accounts_and_flags_future_accounts(pool):
    migration = importlib.import_module("backend.migrations.versions.0205_developer_platform_only")
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        # A temporary table isolates the cohort test from the application's users.
        conn.execute(text("CREATE TEMP TABLE users (name text) ON COMMIT DROP"))
        conn.execute(text("INSERT INTO users (name) VALUES ('existing')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        conn.execute(text("INSERT INTO users (name) VALUES ('new')"))
        assert dict(
            conn.execute(text("SELECT name, developer_platform_only FROM users")).all()
        ) == {
            "existing": False,
            "new": True,
        }

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_signup_flag_survives_profile_edits_and_can_be_disabled(client, pool):
    response = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    assert response.status_code == 201
    registered = response.json()
    headers = {"Authorization": f"Bearer {registered['api_key']}"}
    profile = await client.get("/api/v1/users/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["developer_platform_only"] is True

    for update in [{"display_name": "Developer"}, {}]:
        edited = await client.patch("/api/v1/users/me", headers=headers, json=update)
        assert edited.status_code == 200
        assert edited.json()["developer_platform_only"] is True

    await pool.execute(
        "UPDATE users SET developer_platform_only = false WHERE id = $1", UUID(registered["id"])
    )
    profile = await client.get("/api/v1/users/me", headers=headers)
    assert profile.json()["developer_platform_only"] is False
