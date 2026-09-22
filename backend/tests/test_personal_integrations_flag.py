"""Existing accounts retain connection management without enabling it for new signups."""

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
async def test_rollout_preserves_existing_accounts_and_defaults_new_accounts_off(pool):
    migration = importlib.import_module(
        "backend.migrations.versions.0222_personal_integrations_access"
    )
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    )

    def migrate(conn):
        conn.execute(text("CREATE TEMP TABLE users (name text) ON COMMIT DROP"))
        conn.execute(text("INSERT INTO users VALUES ('existing')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        conn.execute(text("INSERT INTO users (name) VALUES ('new')"))
        assert dict(
            conn.execute(text("SELECT name, personal_integrations_enabled FROM users")).all()
        ) == {
            "existing": True,
            "new": False,
        }

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_flag_is_returned_by_auth_and_profile_edits_but_not_user_editable(client, pool):
    response = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    assert response.status_code == 201
    registered = response.json()
    headers = {"Authorization": f"Bearer {registered['api_key']}"}
    profile = await client.get("/api/v1/users/me", headers=headers)
    assert profile.json()["personal_integrations_enabled"] is False
    await client.patch(
        "/api/v1/users/me", headers=headers, json={"personal_integrations_enabled": True}
    )
    profile = await client.get("/api/v1/users/me", headers=headers)
    assert profile.json()["personal_integrations_enabled"] is False

    await pool.execute(
        "UPDATE users SET personal_integrations_enabled = true WHERE id = $1",
        UUID(registered["id"]),
    )
    for update in [{"display_name": "Existing customer"}, {}]:
        edited = await client.patch("/api/v1/users/me", headers=headers, json=update)
        assert edited.status_code == 200
        assert edited.json()["personal_integrations_enabled"] is True
    profile = await client.get("/api/v1/users/me", headers=headers)
    assert profile.json()["personal_integrations_enabled"] is True
