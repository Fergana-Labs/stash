"""Tests for the GitHub skill importer that bootstraps Discover.

GitHub fetchers are monkeypatched with an in-memory fake repo; everything
downstream (curator seeding, folder/page creation, publish, idempotent
re-import) runs against the real services and DB.
"""

import pytest
from httpx import AsyncClient

from backend.services import github_skill_import as gsi

COOKING_SKILL_MD = b"""---
name: Cooking Wizard
description: Plan and cook a full menu.
---

Use references/guide.md for techniques.
"""

FAKE_REPO = {
    "README.md": b"# Not a skill\n",
    "cooking/SKILL.md": COOKING_SKILL_MD,
    "cooking/references/guide.md": b"# Techniques\n",
    "cooking/logo.png": b"\x89PNG fake bytes",
    "baking/SKILL.md": (
        b"---\nname: Baking Wizard\ndescription: Plan and bake a full menu.\n---\n\nBake.\n"
    ),
}


def _fake_github(monkeypatch, files: dict[str, bytes], branch: str = "main") -> None:
    async def fake_branch(client, owner, repo):
        return branch

    async def fake_tree(client, owner, repo, ref):
        return [{"path": p, "type": "blob", "size": len(b)} for p, b in files.items()]

    async def fake_blob(client, owner, repo, ref, path):
        return files[path]

    monkeypatch.setattr(gsi, "_fetch_default_branch", fake_branch)
    monkeypatch.setattr(gsi, "_fetch_tree", fake_tree)
    monkeypatch.setattr(gsi, "_fetch_blob", fake_blob)


async def _import_repo(repo_url: str) -> list[str]:
    owner_user_id, owner_id = await gsi.ensure_curator()
    results = []
    for skill in await gsi.fetch_repo_skills(repo_url):
        results.append(
            await gsi.import_skill(
                owner_user_id,
                owner_id,
                source_url=skill["source_url"],
                files=skill["files"],
            )
        )
    return results


def test_parse_repo_url():
    assert gsi.parse_repo_url("https://github.com/acme/skills") == ("acme", "skills")
    assert gsi.parse_repo_url("https://github.com/acme/skills.git/") == ("acme", "skills")
    with pytest.raises(ValueError):
        gsi.parse_repo_url("https://gitlab.com/acme/skills")


def test_discover_skill_dirs_finds_root_and_nested():
    tree = [
        {"path": "SKILL.md", "type": "blob"},
        {"path": "sub/SKILL.md", "type": "blob"},
        {"path": "sub/deep/notes.md", "type": "blob"},
        {"path": "plain/README.md", "type": "blob"},
        {"path": "plain", "type": "tree"},
    ]
    assert gsi.discover_skill_dirs(tree) == ["", "sub"]


@pytest.mark.asyncio
async def test_import_publishes_discoverable_skills(client: AsyncClient, pool, monkeypatch):
    _fake_github(monkeypatch, FAKE_REPO)
    results = await _import_repo("https://github.com/acme/skills")
    assert results == ["created", "created"]

    resp = await client.get("/api/v1/discover/skills", params={"sort": "newest"})
    assert resp.status_code == 200
    by_title = {s["title"]: s for s in resp.json()["skills"]}

    cooking = by_title["Cooking Wizard"]
    assert cooking["description"] == "Plan and cook a full menu."
    assert cooking["source_github_url"] == "https://github.com/acme/skills/tree/main/cooking"
    baking = by_title["Baking Wizard"]
    assert baking["description"] == "Plan and bake a full menu."
    assert baking["source_github_url"] == "https://github.com/acme/skills/tree/main/baking"

    # SKILL.md keeps its exact filename because agent harnesses require it and
    # nested reference docs land in a child folder, not the scope root.
    skill_folder = await pool.fetchval(
        "SELECT folder_id FROM skills WHERE id = $1::uuid", cooking["id"]
    )
    skill_md = await pool.fetchrow(
        "SELECT name FROM pages WHERE folder_id = $1 AND name = 'SKILL.md'", skill_folder
    )
    assert skill_md is not None
    guide_folder = await pool.fetchrow(
        "SELECT id FROM folders WHERE parent_folder_id = $1 AND name = 'references'",
        skill_folder,
    )
    assert guide_folder is not None
    guide = await pool.fetchval("SELECT name FROM pages WHERE folder_id = $1", guide_folder["id"])
    assert guide == "guide.md"


@pytest.mark.asyncio
async def test_reimport_updates_in_place(client: AsyncClient, pool, monkeypatch):
    _fake_github(monkeypatch, FAKE_REPO)
    await _import_repo("https://github.com/acme/skills")

    resp = await client.get("/api/v1/discover/skills", params={"q": "Cooking"})
    first = next(s for s in resp.json()["skills"] if s["title"] == "Cooking Wizard")

    updated_repo = {
        "cooking/SKILL.md": b"---\nname: Cooking Pro\ndescription: New blurb.\n---\nBody.\n",
        "cooking/CHANGELOG.md": b"v2\n",
        "baking/SKILL.md": FAKE_REPO["baking/SKILL.md"],
    }
    _fake_github(monkeypatch, updated_repo)
    results = await _import_repo("https://github.com/acme/skills")
    assert results == ["updated", "updated"]

    resp = await client.get("/api/v1/discover/skills", params={"q": "Cooking"})
    second = next(s for s in resp.json()["skills"] if "Cooking" in s["title"])
    assert second["id"] == first["id"]
    assert second["slug"] == first["slug"]
    assert second["title"] == "Cooking Pro"
    assert second["description"] == "New blurb."

    # Old contents are gone, replaced by the new tree — and nothing orphaned
    # into the scope root (pages/files folder FKs are SET NULL on folder
    # delete, which a naive folder-only delete would trigger).
    folder_id = await pool.fetchval(
        "SELECT folder_id FROM skills WHERE id = $1::uuid", second["id"]
    )
    names = {
        r["name"]
        for r in await pool.fetch("SELECT name FROM pages WHERE folder_id = $1", folder_id)
    }
    assert names == {"SKILL.md", "CHANGELOG.md"}
    owner_user_id = await pool.fetchval(
        "SELECT owner_user_id FROM skills WHERE id = $1::uuid", second["id"]
    )
    orphans = await pool.fetchval(
        "SELECT COUNT(*) FROM pages WHERE owner_user_id = $1 AND folder_id IS NULL",
        owner_user_id,
    )
    assert orphans == 0


@pytest.mark.asyncio
async def test_import_requires_skill_md(pool):
    owner_user_id, owner_id = await gsi.ensure_curator()
    with pytest.raises(ValueError, match="no SKILL.md"):
        await gsi.import_skill(
            owner_user_id,
            owner_id,
            source_url="https://github.com/acme/empty",
            files=[("README.md", b"hi")],
        )


@pytest.mark.asyncio
async def test_import_rejects_invalid_skill_metadata(pool):
    owner_user_id, owner_id = await gsi.ensure_curator()
    with pytest.raises(ValueError, match="non-empty `description`"):
        await gsi.import_skill(
            owner_user_id,
            owner_id,
            source_url="https://github.com/acme/invalid",
            files=[("SKILL.md", b"---\nname: invalid\ndescription:\n---\n")],
        )
