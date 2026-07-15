"""Tests for user registration, login, and API key authentication."""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import user_service

from .conftest import unique_name


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    name = unique_name()
    resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": name,
            "password": "securepassword1",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == name
    assert body["api_key"].startswith("st_")


@pytest.mark.asyncio
async def test_register_duplicate_name(client: AsyncClient):
    name = unique_name()
    payload = {"name": name, "password": "securepassword1"}
    await client.post("/api/v1/users/register", json=payload)
    resp = await client.post("/api/v1/users/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_short_password(client: AsyncClient):
    resp = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name(),
            "password": "short",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    name = unique_name()
    password = "correctpassword1"
    reg = await client.post(
        "/api/v1/users/register",
        json={
            "name": name,
            "password": password,
        },
    )
    assert reg.status_code == 201

    login = await client.post("/api/v1/users/login", json={"name": name, "password": password})
    assert login.status_code == 200
    assert login.json()["api_key"].startswith("st_")


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    name = unique_name()
    await client.post(
        "/api/v1/users/register",
        json={
            "name": name,
            "password": "correctpassword1",
        },
    )
    resp = await client.post(
        "/api/v1/users/login", json={"name": name, "password": "wrongpassword"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_auth(client: AsyncClient):
    name = unique_name()
    reg = await client.post(
        "/api/v1/users/register",
        json={
            "name": name,
            "password": "securepassword1",
            "email": "henry@example.com",
        },
    )
    api_key = reg.json()["api_key"]

    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {api_key}"})
    assert me.status_code == 200
    assert me.json()["name"] == name
    assert me.json()["email"] == "henry@example.com"


@pytest.mark.asyncio
async def test_logout_revokes_current_api_key(client: AsyncClient):
    reg = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name(),
            "password": "securepassword1",
        },
    )
    api_key = reg.json()["api_key"]

    logout = await client.post(
        "/api/v1/users/logout",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert logout.status_code == 204

    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {api_key}"})
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_cli_auth_approve_then_poll_returns_usable_device_key(client: AsyncClient, pool):
    reg = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("cli_auth"),
            "password": "securepassword1",
        },
    )
    api_key = reg.json()["api_key"]

    session = await client.post(
        "/api/v1/users/cli-auth/sessions",
        json={"device_name": "demo-laptop"},
    )
    assert session.status_code == 200
    session_id = session.json()["session_id"]

    approved = await client.post(
        f"/api/v1/users/cli-auth/sessions/{session_id}/approve",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert approved.status_code == 200

    polled = await client.get(f"/api/v1/users/cli-auth/sessions/{session_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "complete"
    assert body["api_key"].startswith("st_")

    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM cli_auth_sessions WHERE session_id = $1",
            session_id,
        )
        == 0
    )
    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['api_key']}"},
    )
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_cli_auth_approve_is_idempotent_and_leaves_no_orphan_key(
    client: AsyncClient,
    pool,
):
    reg = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("cli_auth_replay"),
            "password": "securepassword1",
        },
    )
    api_key = reg.json()["api_key"]
    user_id = UUID(reg.json()["id"])

    session = await client.post(
        "/api/v1/users/cli-auth/sessions",
        json={"device_name": "replayed-laptop"},
    )
    assert session.status_code == 200
    session_id = session.json()["session_id"]
    headers = {"Authorization": f"Bearer {api_key}"}

    first = await client.post(
        f"/api/v1/users/cli-auth/sessions/{session_id}/approve", headers=headers
    )
    assert first.status_code == 200
    minted_key = await pool.fetchval(
        "SELECT api_key FROM cli_auth_sessions WHERE session_id = $1", session_id
    )

    # A replayed approve must not mint a second key. The session keeps its one
    # key, and the count of live keys for this user stays at exactly one.
    second = await client.post(
        f"/api/v1/users/cli-auth/sessions/{session_id}/approve", headers=headers
    )
    assert second.status_code == 200
    assert (
        await pool.fetchval(
            "SELECT api_key FROM cli_auth_sessions WHERE session_id = $1", session_id
        )
        == minted_key
    )

    live_cli_keys = await pool.fetchval(
        "SELECT COUNT(*) FROM user_api_keys "
        "WHERE user_id = $1 AND name LIKE 'CLI %' AND revoked_at IS NULL",
        user_id,
    )
    assert live_cli_keys == 1


@pytest.mark.asyncio
async def test_expired_cli_auth_approval_revokes_unclaimed_device_key(
    client: AsyncClient,
    pool,
):
    reg = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("cli_auth_expired"),
            "password": "securepassword1",
        },
    )
    api_key = reg.json()["api_key"]

    session = await client.post(
        "/api/v1/users/cli-auth/sessions",
        json={"device_name": "abandoned-terminal"},
    )
    assert session.status_code == 200
    session_id = session.json()["session_id"]

    approved = await client.post(
        f"/api/v1/users/cli-auth/sessions/{session_id}/approve",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert approved.status_code == 200
    unclaimed_key = await pool.fetchval(
        "SELECT api_key FROM cli_auth_sessions WHERE session_id = $1",
        session_id,
    )
    assert unclaimed_key.startswith("st_")

    await pool.execute(
        "UPDATE cli_auth_sessions "
        "SET created_at = now() - interval '11 minutes' "
        "WHERE session_id = $1",
        session_id,
    )

    polled = await client.get(f"/api/v1/users/cli-auth/sessions/{session_id}")
    assert polled.status_code == 404

    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM cli_auth_sessions WHERE session_id = $1",
            session_id,
        )
        == 0
    )
    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {unclaimed_key}"},
    )
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_scheduled_cleanup_revokes_expired_unclaimed_cli_keys(client: AsyncClient, pool):
    """Beat runs this cleanup directly so an approved-but-never-claimed key is
    revoked even on a deployment with no further cli-auth traffic — otherwise
    the plaintext key would sit live in cli_auth_sessions indefinitely."""
    reg = await client.post(
        "/api/v1/users/register",
        json={
            "name": unique_name("cli_auth_beat"),
            "password": "securepassword1",
        },
    )
    api_key = reg.json()["api_key"]

    session = await client.post(
        "/api/v1/users/cli-auth/sessions",
        json={"device_name": "quiet-deployment"},
    )
    session_id = session.json()["session_id"]
    approved = await client.post(
        f"/api/v1/users/cli-auth/sessions/{session_id}/approve",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert approved.status_code == 200
    unclaimed_key = await pool.fetchval(
        "SELECT api_key FROM cli_auth_sessions WHERE session_id = $1",
        session_id,
    )

    await pool.execute(
        "UPDATE cli_auth_sessions "
        "SET created_at = now() - interval '11 minutes' "
        "WHERE session_id = $1",
        session_id,
    )

    revoked = await user_service.cleanup_expired_cli_auth_sessions()

    assert revoked == 1
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM cli_auth_sessions WHERE session_id = $1",
            session_id,
        )
        == 0
    )
    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {unclaimed_key}"},
    )
    assert me.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["st_", "mc_"])
async def test_invalid_api_key_rejected(client: AsyncClient, prefix: str):
    """Both prefixes route to API-key auth: st_ is current, mc_ is the
    pre-rename prefix that issued keys still carry."""
    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {prefix}fakekeyxxxx"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_issued_mc_key_still_authenticates(client: AsyncClient, pool):
    """Keys minted before the st_ rename are hashed server-side and held raw
    by users (including customer prod deployments) — they must keep working."""
    from backend.auth import hash_api_key

    reg = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("legacy_key"), "password": "securepassword1"},
    )
    user_id = reg.json()["id"]
    legacy_key = "mc_legacy_key_from_before_the_rename"
    await pool.execute(
        "INSERT INTO user_api_keys (user_id, key_hash, name, key_type) VALUES ($1, $2, $3, $4)",
        UUID(user_id),
        hash_api_key(legacy_key),
        "legacy",
        "manual",
    )

    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {legacy_key}"})
    assert me.status_code == 200
    assert me.json()["id"] == user_id


@pytest.mark.asyncio
async def test_missing_auth_rejected(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401
