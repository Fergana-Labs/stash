"""Tests for the public Stash Discover catalog."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    name = name or unique_name()
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name, "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _scope(user: dict) -> dict:
    """The scope is the user: its id is the owner_user_id, its name is the
    owner's display name (what Discover surfaces as `owner_name`)."""
    return {"id": user["id"], "name": user["display_name"]}


async def _create_skill_folder(
    client: AsyncClient,
    api_key: str,
    owner_user_id: str,
    folder_name: str,
    skill_name: str,
    description: str,
) -> str:
    folder = await client.post(
        "/api/v1/me/folders",
        json={"name": folder_name, "is_skill": True},
        headers=_auth(api_key),
    )
    assert folder.status_code == 201
    folder_id = folder.json()["id"]
    page = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": "SKILL.md",
            "content": (
                f"---\nname: {skill_name}\ndescription: {description}\n---\n\n# {skill_name}"
            ),
            "folder_id": folder_id,
        },
        headers=_auth(api_key),
    )
    assert page.status_code == 201
    content_page = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": f"{folder_name} brief",
            "content": f"# {folder_name}",
            "folder_id": folder_id,
        },
        headers=_auth(api_key),
    )
    assert content_page.status_code == 201
    return folder_id


@pytest.mark.asyncio
async def test_discover_lists_discoverable_public_product_stashes(client: AsyncClient):
    api_key, user = await _register(client)
    scope = _scope(user)
    unlisted_folder = await _create_skill_folder(
        client, api_key, scope["id"], "Unlisted", "Public but unlisted", "Unlisted notes."
    )
    public_folder = await _create_skill_folder(
        client, api_key, scope["id"], "Public notes", "Public notes", "A public Stash"
    )

    public_unlisted = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": unlisted_folder, "title": "Public but unlisted"},
        headers=_auth(api_key),
    )
    assert public_unlisted.status_code == 201

    published = await client.post(
        "/api/v1/me/skills",
        json={
            "folder_id": public_folder,
            "title": "Public notes",
            "description": "A public Stash",
            "discoverable": True,
        },
        headers=_auth(api_key),
    )
    assert published.status_code == 201
    published_skill = published.json()
    slug = published_skill["slug"]
    assert published_skill["owner_name"] == user["name"]
    assert published_skill["owner_display_name"] == user["display_name"]

    owned_skills = await client.get(
        "/api/v1/me/skills",
        headers=_auth(api_key),
    )
    assert owned_skills.status_code == 200
    owned_skill = next(
        skill
        for skill in owned_skills.json()["skills"]
        if skill["published"] and skill["published"]["slug"] == slug
    )
    assert owned_skill["folder_id"] == public_folder
    assert owned_skill["published"]["discoverable"] is True

    catalog = await client.get("/api/v1/discover/skills")
    assert catalog.status_code == 200
    skills = catalog.json()["skills"]
    assert [skill["title"] for skill in skills] == ["Public notes"]
    assert skills[0]["slug"] == slug
    assert skills[0]["discoverable"] is True
    # Live count of the folder subtree: the content page + the auto-minted SKILL.md.
    assert skills[0]["item_count"] == 2
    assert skills[0]["owner_name"] == scope["name"]
    # GitHub attribution is import-only; organic publishes carry null.
    assert skills[0]["source_github_url"] is None

    detail = await client.get(f"/api/v1/skills/{slug}")
    assert detail.status_code == 200
    assert detail.json()["skill"]["discoverable"] is True
    assert detail.json()["skill"]["owner_name"] == user["name"]
    assert detail.json()["skill"]["owner_display_name"] == user["display_name"]

    unlisted_detail = await client.get(f"/api/v1/skills/{public_unlisted.json()['slug']}")
    assert unlisted_detail.status_code == 200


@pytest.mark.asyncio
async def test_unlisted_skill_public_by_slug_but_absent_from_discover(client: AsyncClient):
    """Discoverable is purely an opt-in catalog flag: a default publish is
    publicly readable at its slug (anonymously) yet never surfaces in
    Discover."""
    api_key, user = await _register(client)
    scope = _scope(user)
    folder_id = await _create_skill_folder(
        client, api_key, scope["id"], "Unlisted only", "Unlisted only", "Unlisted notes."
    )

    published = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder_id, "title": "Unlisted only"},
        headers=_auth(api_key),
    )
    assert published.status_code == 201
    slug = published.json()["slug"]

    catalog = await client.get("/api/v1/discover/skills")
    assert catalog.status_code == 200
    assert slug not in {skill["slug"] for skill in catalog.json()["skills"]}

    # Anonymous read by slug still works — published == public.
    detail = await client.get(f"/api/v1/skills/{slug}")
    assert detail.status_code == 200
    assert detail.json()["skill"]["discoverable"] is False


@pytest.mark.asyncio
async def test_discover_search_filters_product_stashes(client: AsyncClient):
    api_key, user = await _register(client)
    scope = _scope(user)

    for title, folder_name in (("Alpha launch notes", "Alpha"), ("Beta roadmap", "Beta")):
        folder_id = await _create_skill_folder(
            client, api_key, scope["id"], folder_name, title, f"Search for {folder_name}."
        )
        resp = await client.post(
            "/api/v1/me/skills",
            json={"folder_id": folder_id, "title": title, "discoverable": True},
            headers=_auth(api_key),
        )
        assert resp.status_code == 201

    filtered = await client.get("/api/v1/discover/skills?q=alpha")
    assert filtered.status_code == 200
    assert [skill["title"] for skill in filtered.json()["skills"]] == ["Alpha launch notes"]
