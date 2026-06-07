"""Tests for Auth0 user provisioning.

The `created` flag is the contract the frontend relies on to route first-time
Auth0 sign-ins into onboarding (instead of dropping them on their workspace
like a returning user). If this flag stops distinguishing new from returning
users, new Google-OAuth users silently skip onboarding.
"""

import pytest

from backend.managed.auth0.users import (
    get_or_create_user_from_auth0,
    get_or_create_user_row_from_auth0,
)

from .conftest import unique_name


@pytest.fixture(autouse=True)
async def _managed_auth0_schema(pool):
    """Auth0 lives in the managed migration chain (backend/managed/migrations),
    which the test DB doesn't apply. Mirror m0001 so users.auth0_sub exists."""
    await pool.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth0_sub VARCHAR(128) UNIQUE")


@pytest.mark.asyncio
async def test_first_exchange_reports_created(pool):
    sub = f"google-oauth2|{unique_name()}"
    user, api_key, created = await get_or_create_user_from_auth0(
        auth0_sub=sub, email=None, name="New Person"
    )
    assert created is True
    assert api_key.startswith("mc_")
    # First sign-in provisions a workspace, so a workspace lookup alone can't
    # tell new from returning — only `created` can.
    ws_count = await pool.fetchval(
        "SELECT count(*) FROM workspace_members WHERE user_id = $1", user["id"]
    )
    assert ws_count == 1


@pytest.mark.asyncio
async def test_repeat_exchange_reports_not_created(pool):
    sub = f"google-oauth2|{unique_name()}"
    first_user, _api_key, _created = await get_or_create_user_from_auth0(
        auth0_sub=sub, email=None, name="Returning Person"
    )
    await pool.execute(
        "UPDATE users SET created_at = now() - interval '1 hour' WHERE id = $1",
        first_user["id"],
    )
    _user, _api_key, created = await get_or_create_user_from_auth0(
        auth0_sub=sub, email=None, name="Returning Person"
    )
    assert created is False


@pytest.mark.asyncio
async def test_immediate_duplicate_exchange_still_reports_created(pool):
    sub = f"google-oauth2|{unique_name()}"
    await get_or_create_user_from_auth0(auth0_sub=sub, email=None, name="Strict Mode Person")
    _user, _api_key, created = await get_or_create_user_from_auth0(
        auth0_sub=sub, email=None, name="Strict Mode Person"
    )
    assert created is True


@pytest.mark.asyncio
async def test_browser_session_provisioning_does_not_mint_api_key(pool):
    sub = f"google-oauth2|{unique_name()}"
    user, created = await get_or_create_user_row_from_auth0(
        auth0_sub=sub,
        email=None,
        name="Browser Session Person",
    )
    assert created is True

    key_count = await pool.fetchval(
        "SELECT count(*) FROM user_api_keys WHERE user_id = $1",
        user["id"],
    )
    assert key_count == 0
