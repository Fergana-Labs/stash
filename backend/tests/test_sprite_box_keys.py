"""Box key hygiene: provisioning never leaks "cloud computer" API keys.

Every provision and reseed mints a machine key and bakes it into the box, but
the box only ever holds one — so a successful seed must revoke the keys it
supersedes, and a failed attempt must revoke the key it minted. Without this,
identical "cloud computer" keys pile up in the user's API-key list (Heavi's
console showed five).
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend import auth
from backend.config import settings
from backend.database import get_pool
from backend.services import sprite_service

from .conftest import unique_name


async def _register(client: AsyncClient) -> UUID:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("boxkeys"), "password": "securepassword1"},
    )
    assert r.status_code == 201
    return UUID(r.json()["id"])


async def _box_keys(user_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT key_hash, revoked_at FROM user_api_keys "
        "WHERE user_id = $1 AND key_type = 'machine' AND name = 'cloud computer' "
        "ORDER BY created_at",
        user_id,
    )
    return [dict(r) for r in rows]


async def _stale_ready_row(user_id: UUID) -> None:
    await get_pool().execute(
        "INSERT INTO user_sprites (user_id, sprite_name, status, seed_version) "
        "VALUES ($1, $2, 'ready', 0)",
        user_id,
        f"stash-u-{user_id.hex}",
    )


@pytest.fixture
def sprites_mode(monkeypatch):
    """acquire() in sprites mode: the box is confirmed alive, the Sprites REST
    API is a no-op, and seed execs succeed."""
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def exists(name):
        return True

    async def fake_sprites_api(method, path, *, json=None):
        return {}

    async def ok_exec(sprite, argv, *, env, cwd=None, timeout_s, stdout_only=False):
        return ("", 0)

    monkeypatch.setattr(sprite_service, "_sprite_exists", exists)
    monkeypatch.setattr(sprite_service, "_sprites_api", fake_sprites_api)
    monkeypatch.setattr(sprite_service, "exec_collect", ok_exec)
    return monkeypatch


def _failing_exec(monkeypatch):
    async def failing(sprite, argv, *, env, cwd=None, timeout_s, stdout_only=False):
        return ("curl: could not resolve host", 6)

    monkeypatch.setattr(sprite_service, "exec_collect", failing)


@pytest.mark.asyncio
async def test_reseed_revokes_the_superseded_key(client: AsyncClient, sprites_mode):
    user_id = await _register(client)
    await _stale_ready_row(user_id)
    old_key = await auth.create_api_key(user_id, name="cloud computer", key_type="machine")

    await sprite_service.acquire(user_id)

    keys = await _box_keys(user_id)
    assert len(keys) == 2
    old = next(k for k in keys if k["key_hash"] == auth.hash_api_key(old_key))
    assert old["revoked_at"] is not None
    assert sum(1 for k in keys if k["revoked_at"] is None) == 1


@pytest.mark.asyncio
async def test_failed_reseed_revokes_its_key_and_keeps_the_live_one(
    client: AsyncClient, sprites_mode
):
    user_id = await _register(client)
    await _stale_ready_row(user_id)
    live_key = await auth.create_api_key(user_id, name="cloud computer", key_type="machine")
    _failing_exec(sprites_mode)

    with pytest.raises(sprite_service.SpriteError, match="reseed exited 6"):
        await sprite_service.acquire(user_id)

    keys = await _box_keys(user_id)
    assert len(keys) == 2
    # The box still runs on its last good seed, so its key must survive.
    live = next(k for k in keys if k["key_hash"] == auth.hash_api_key(live_key))
    assert live["revoked_at"] is None
    minted = next(k for k in keys if k["key_hash"] != auth.hash_api_key(live_key))
    assert minted["revoked_at"] is not None


@pytest.mark.asyncio
async def test_provision_leaves_exactly_one_live_key(client: AsyncClient, sprites_mode):
    user_id = await _register(client)

    await sprite_service.acquire(user_id)

    keys = await _box_keys(user_id)
    assert len(keys) == 1
    assert keys[0]["revoked_at"] is None


@pytest.mark.asyncio
async def test_failed_provision_revokes_the_minted_key(client: AsyncClient, sprites_mode):
    user_id = await _register(client)
    _failing_exec(sprites_mode)

    with pytest.raises(sprite_service.SpriteError, match="seed script exited 6"):
        await sprite_service.acquire(user_id)

    keys = await _box_keys(user_id)
    assert len(keys) == 1
    assert keys[0]["revoked_at"] is not None
