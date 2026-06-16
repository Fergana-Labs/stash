"""The default-skills registry seeds slides + build-on-stash into a workspace."""

import os
import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import skill_seeds


@pytest.fixture
def enable_seed():
    prev = os.environ.pop(skill_seeds.DISABLE_ENV_VAR, None)
    try:
        yield
    finally:
        if prev is not None:
            os.environ[skill_seeds.DISABLE_ENV_VAR] = prev


async def _register_and_workspace(client: AsyncClient) -> tuple[UUID, UUID]:
    name = f"user_{uuid.uuid4().hex[:10]}"
    reg = (
        await client.post(
            "/api/v1/users/register",
            json={"name": name, "display_name": name, "password": "password123"},
        )
    ).json()
    ws = (
        await client.post(
            "/api/v1/workspaces",
            json={"name": "S"},
            headers={"Authorization": f"Bearer {reg['api_key']}"},
        )
    ).json()
    return UUID(ws["id"]), UUID(reg["id"])


@pytest.mark.asyncio
async def test_seeds_both_default_skills(client: AsyncClient, pool, enable_seed):
    ws_id, user_id = await _register_and_workspace(client)
    await skill_seeds.seed_default_skills(ws_id, user_id)

    folders = await pool.fetch(
        "SELECT lower(f.name) AS folder FROM pages p JOIN folders f ON f.id = p.folder_id "
        "WHERE f.workspace_id = $1 AND p.name = 'SKILL.md' AND p.deleted_at IS NULL",
        ws_id,
    )
    names = {r["folder"] for r in folders}
    assert "slides" in names
    assert "build-on-stash" in names


@pytest.mark.asyncio
async def test_seed_is_idempotent(client: AsyncClient, pool, enable_seed):
    ws_id, user_id = await _register_and_workspace(client)
    await skill_seeds.seed_default_skills(ws_id, user_id)
    await skill_seeds.seed_default_skills(ws_id, user_id)  # second run must not duplicate

    count = await pool.fetchval(
        "SELECT COUNT(*) FROM pages p JOIN folders f ON f.id = p.folder_id "
        "WHERE f.workspace_id = $1 AND lower(f.name) = 'build-on-stash' AND p.name = 'SKILL.md'",
        ws_id,
    )
    assert count == 1
