"""Launching a published skill: frontmatter lists, and installing before a run.

An agent resolves skills from its own scope, never from the Discover catalog,
so the launcher has to put a public skill in the caller's scope first. That has
to be idempotent — the launcher calls it on *every* run.
"""

from httpx import AsyncClient

from backend.services import shared_skill_service, skill_service

from .conftest import unique_name

LIBRARY_SKILL_MD = """---
name: resurface
description: Old saves worth revisiting.
when_to_use: When the user asks what they have forgotten.
examples:
  - What should I revisit this week?
  - Find old saves about agents.
version: "1"
---

Body.
"""


def test_frontmatter_reads_block_lists():
    meta, body = skill_service.parse_frontmatter(LIBRARY_SKILL_MD)

    assert meta["examples"] == [
        "What should I revisit this week?",
        "Find old saves about agents.",
    ]
    # Scalars either side of the list still parse, and the list doesn't swallow
    # the key that follows it.
    assert meta["name"] == "resurface"
    assert meta["version"] == "1"
    assert body.strip() == "Body."


def test_a_key_with_nothing_listed_under_it_stays_a_string():
    """Half the skills in the wild carry a bare `description:`. Turning that
    into [] would change what every existing reader of it sees."""
    meta, _body = skill_service.parse_frontmatter("---\nname: x\ndescription:\n---\nbody\n")

    assert meta["description"] == ""


def test_frontmatter_examples_ignores_a_scalar():
    meta, _body = skill_service.parse_frontmatter("---\nexamples: not a list\n---\nbody\n")

    assert skill_service.frontmatter_examples(meta) == []


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
        json={"folder_id": folder_id, "title": "resurface", "discoverable": True},
        headers=headers,
    )
    return published.json()["slug"]


async def test_install_puts_a_public_skill_in_the_callers_scope(client: AsyncClient):
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


async def test_installing_twice_does_not_make_a_second_copy(client: AsyncClient):
    """Every launch installs first. If that forked each time, a user who ran
    the same skill five times would end up choosing between "resurface (5)"
    and the original — and the agent would resolve the wrong one."""
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


async def test_install_rejects_an_unknown_slug(client: AsyncClient):
    _runner, headers = await _register(client)

    response = await client.post(
        "/api/v1/me/skills/install", json={"slug": "no-such-skill"}, headers=headers
    )

    assert response.status_code == 404


async def test_discover_carries_the_starter_prompts(client: AsyncClient):
    """A skill you have not installed still has to be launchable, so its
    frontmatter has to reach the catalog — the skills row alone doesn't
    carry when_to_use or examples."""
    _author, author_headers = await _register(client)
    await _publish_skill(client, author_headers, LIBRARY_SKILL_MD)

    catalog = await client.get("/api/v1/discover/skills")
    card = next(s for s in catalog.json()["skills"] if s["title"] == "resurface")

    assert card["examples"] == [
        "What should I revisit this week?",
        "Find old saves about agents.",
    ]
    assert card["when_to_use"] == "When the user asks what they have forgotten."


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
    assert found[0]["examples"][0] == "What should I revisit this week?"
