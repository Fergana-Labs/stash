"""Seed versioning: boxes provisioned under an older seed script re-run it.

Sprites are seeded once at provision, so seed additions (the opencode install)
never reached older boxes — their managed-harness runs died on "command not
found". acquire() must re-seed a stale box exactly once, and leave current
boxes alone.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.config import settings
from backend.database import get_pool
from backend.services import sprite_service

from .conftest import unique_name


async def _register(client: AsyncClient) -> UUID:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("sprite"), "password": "securepassword1"},
    )
    assert r.status_code == 201
    return UUID(r.json()["id"])


@pytest.fixture
def sprites_mode(monkeypatch):
    """acquire() in sprites mode with the box confirmed alive; seed execs are
    captured instead of hitting the Sprites API."""
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def exists(name):
        return True

    seeds: list[list[str]] = []

    async def fake_exec_collect(sprite, argv, *, env, cwd=None, timeout_s, stdout_only=False):
        seeds.append(argv)
        return ("", 0)

    monkeypatch.setattr(sprite_service, "_sprite_exists", exists)
    monkeypatch.setattr(sprite_service, "exec_collect", fake_exec_collect)
    return seeds


@pytest.mark.asyncio
async def test_stale_seed_reruns_once_on_acquire(client: AsyncClient, sprites_mode):
    user_id = await _register(client)
    await get_pool().execute(
        "INSERT INTO user_sprites (user_id, sprite_name, status, seed_version) "
        "VALUES ($1, $2, 'ready', 0)",
        user_id,
        f"stash-u-{user_id.hex}",
    )

    sprite = await sprite_service.acquire(user_id)
    assert sprite.name == f"stash-u-{user_id.hex}"
    assert len(sprites_mode) == 1
    assert "opencode" in sprites_mode[0][2]  # the seed script installs opencode

    row = await get_pool().fetchrow(
        "SELECT seed_version FROM user_sprites WHERE user_id = $1", user_id
    )
    assert row["seed_version"] == sprite_service.SEED_VERSION

    # Now current: acquiring again must not seed a second time.
    await sprite_service.acquire(user_id)
    assert len(sprites_mode) == 1


@pytest.mark.asyncio
async def test_failed_reseed_resets_version_for_retry(client: AsyncClient, monkeypatch):
    user_id = await _register(client)
    await get_pool().execute(
        "INSERT INTO user_sprites (user_id, sprite_name, status, seed_version) "
        "VALUES ($1, $2, 'ready', 0)",
        user_id,
        f"stash-u-{user_id.hex}",
    )
    monkeypatch.setattr(settings, "AGENT_EXEC_MODE", "sprites")

    async def exists(name):
        return True

    async def failing_exec_collect(sprite, argv, *, env, cwd=None, timeout_s, stdout_only=False):
        return ("curl: could not resolve host", 6)

    monkeypatch.setattr(sprite_service, "_sprite_exists", exists)
    monkeypatch.setattr(sprite_service, "exec_collect", failing_exec_collect)

    with pytest.raises(sprite_service.SpriteError, match="reseed exited 6"):
        await sprite_service.acquire(user_id)

    row = await get_pool().fetchrow(
        "SELECT seed_version FROM user_sprites WHERE user_id = $1", user_id
    )
    assert row["seed_version"] == 0  # stale again — the next acquire retries
