"""Tests for the default slides skill seeded into every workspace.

The conftest disables the auto-seed (so empty-state assertions across
the rest of the suite stay clean). These tests opt back in by calling
`seed_slides_skill` directly with the disable knob cleared, then verify
the skill is discoverable via the workspace skills API.
"""

import os

import pytest
from httpx import AsyncClient

from backend.services import skill_seeds

from .conftest import unique_name


@pytest.fixture
def enable_seed():
    """Temporarily un-set the test-mode disable knob so seed runs."""
    prev = os.environ.pop(skill_seeds.DISABLE_ENV_VAR, None)
    try:
        yield
    finally:
        if prev is not None:
            os.environ[skill_seeds.DISABLE_ENV_VAR] = prev


async def _register_user(client: AsyncClient) -> tuple[str, str]:
    """Returns (api_key, owner_user_id) for a freshly registered user.

    The scope is the user, so owner_user_id is just the user's id."""
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    api_key = resp.json()["api_key"]
    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert me.status_code == 200
    return api_key, me.json()["id"]


async def _seed(owner_user_id: str) -> None:
    """Run the seed against the scope as the registered owner."""
    from uuid import UUID

    await skill_seeds.seed_slides_skill(UUID(owner_user_id), UUID(owner_user_id))


@pytest.mark.asyncio
async def test_seeded_workspace_has_slides_skill(client: AsyncClient, enable_seed):
    api_key, owner_user_id = await _register_user(client)
    await _seed(owner_user_id)

    resp = await client.get(
        f"/api/v1/workspaces/{owner_user_id}/skills",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    names = [s["name"] for s in skills]
    assert "slides" in names, f"slides skill missing after seed: {names}"


@pytest.mark.asyncio
async def test_slides_skill_body_covers_canvas(client: AsyncClient, enable_seed):
    """The seeded SKILL.md must teach the 1920x1080 canvas — that's the
    whole reason the skill exists. Guard against an accidental edit that
    drops the dimension constraint."""
    api_key, owner_user_id = await _register_user(client)
    await _seed(owner_user_id)

    resp = await client.get(
        f"/api/v1/workspaces/{owner_user_id}/skills/slides",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    combined = body.get("combined", "") or body.get("body", "")
    assert (
        "1920" in combined and "1080" in combined
    ), "slides skill must spell out the canvas dimensions so agents stop overflowing"
    assert (
        '<section class="slide">' in combined or "section.slide" in combined
    ), "slides skill must spell out the slide element format"


@pytest.mark.asyncio
async def test_seed_is_idempotent(client: AsyncClient, enable_seed):
    """Re-running the seed shouldn't create duplicate folders or pages."""
    api_key, owner_user_id = await _register_user(client)
    await _seed(owner_user_id)
    await _seed(owner_user_id)

    resp = await client.get(
        f"/api/v1/workspaces/{owner_user_id}/skills",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    slides_skills = [s for s in resp.json()["skills"] if s["name"] == "slides"]
    assert len(slides_skills) == 1, f"expected one slides skill, got {len(slides_skills)}"
