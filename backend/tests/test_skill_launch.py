"""Adding a published skill, which is what has to happen before it can be run.

An agent resolves skills from its own scope, never from the Discover catalog.
Adding is always the user's explicit act — nothing runs a skill you did not
add — but it has to be idempotent, because Add is a button people press twice.
"""

from httpx import AsyncClient

from backend.services import shared_skill_service

from .conftest import unique_name

LIBRARY_SKILL_MD = """---
name: resurface
description: Old saves worth revisiting.
when_to_use: When the user asks what they have forgotten.
version: "1"
---

Body.
"""


async def _register(client: AsyncClient) -> tuple[dict, dict]:
    response = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    body = response.json()
    return body, {"Authorization": f"Bearer {body['api_key']}"}


async def _publish_skill(client: AsyncClient, headers: dict, markdown: str) -> str:
    """Publish a skill from a fresh scope and return its public slug."""
    folder = await client.post("/api/v1/me/folders", json={"name": "resurface"}, headers=headers)
    folder_id = folder.json()["id"]
    page = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "SKILL.md", "folder_id": folder_id, "content": markdown},
        headers=headers,
    )
    assert page.status_code == 201, page.text
    published = await client.post(
        "/api/v1/me/skills",
        json={
            "folder_id": folder_id,
            "title": "resurface",
            # The curator import copies this off the frontmatter, so a curated
            # skill always has one on the row — which is what the strip reads.
            "description": "Old saves worth revisiting.",
            "discoverable": True,
        },
        headers=headers,
    )
    return published.json()["slug"]


async def test_add_puts_a_public_skill_in_the_callers_scope(client: AsyncClient):
    _author, author_headers = await _register(client)
    slug = await _publish_skill(client, author_headers, LIBRARY_SKILL_MD)
    _runner, runner_headers = await _register(client)

    response = await client.post(
        "/api/v1/me/skills/install", json={"slug": slug}, headers=runner_headers
    )

    assert response.status_code == 200
    assert response.json()["installed"] is True
    held = await client.get("/api/v1/me/skills", headers=runner_headers)
    assert [s["name"] for s in held.json()["skills"]] == ["resurface"]


async def test_adding_twice_does_not_make_a_second_copy(client: AsyncClient):
    """Add is a button, and buttons get pressed twice. If the second press
    forked, the user would end up choosing between "resurface" and
    "resurface (2)" with the agent resolving whichever it found first."""
    _author, author_headers = await _register(client)
    slug = await _publish_skill(client, author_headers, LIBRARY_SKILL_MD)
    _runner, runner_headers = await _register(client)

    first = await client.post(
        "/api/v1/me/skills/install", json={"slug": slug}, headers=runner_headers
    )
    second = await client.post(
        "/api/v1/me/skills/install", json={"slug": slug}, headers=runner_headers
    )

    assert second.json()["installed"] is False
    assert second.json()["folder_id"] == first.json()["folder_id"]
    held = await client.get("/api/v1/me/skills", headers=runner_headers)
    assert [s["name"] for s in held.json()["skills"]] == ["resurface"]


async def test_add_rejects_an_unknown_slug(client: AsyncClient):
    _runner, headers = await _register(client)

    response = await client.post(
        "/api/v1/me/skills/install", json={"slug": "no-such-skill"}, headers=headers
    )

    assert response.status_code == 404


async def test_a_published_skill_is_not_in_your_scope_until_you_add_it(client: AsyncClient):
    """The reason Add exists at all: publishing to Discover puts a skill in the
    catalog, not in anyone's Skills, so an agent cannot reach it."""
    _author, author_headers = await _register(client)
    await _publish_skill(client, author_headers, LIBRARY_SKILL_MD)
    _runner, runner_headers = await _register(client)

    held = await client.get("/api/v1/me/skills", headers=runner_headers)

    assert held.json()["skills"] == []


async def test_curated_skills_resolve_by_name(client: AsyncClient, pool):
    """The Bookmarks strip names the skills it wants; slugs carry a random
    suffix and would go stale on the first republish."""
    _author, author_headers = await _register(client)
    await _publish_skill(client, author_headers, LIBRARY_SKILL_MD)
    author_id = await pool.fetchval("SELECT owner_user_id FROM skills WHERE title = 'resurface'")
    await pool.execute(
        "UPDATE users SET name = $1 WHERE id = $2",
        shared_skill_service.CURATOR_USERNAME,
        author_id,
    )

    found = await shared_skill_service.curated_skills_by_name(["resurface", "not-published"])

    assert [s["name"] for s in found] == ["resurface"]
    assert found[0]["description"] == "Old saves worth revisiting."


async def test_curated_lookup_ignores_skills_outside_the_service_account(client: AsyncClient, pool):
    """Anyone can publish a skill called "resurface". The strip must offer the
    Stash-authored one, not whichever row happens to match the name."""
    _author, author_headers = await _register(client)
    await _publish_skill(client, author_headers, LIBRARY_SKILL_MD)

    found = await shared_skill_service.curated_skills_by_name(["resurface"])

    assert found == []
