"""The admin discover-skills endpoints let an operator import/list/remove
GitHub skill repos from the dashboard. GitHub fetchers are faked; these lock
in the X-Admin-Token gate, the import->list->remove round trip, and the
re-import-is-idempotent contract the dashboard relies on."""

import pytest
from httpx import AsyncClient

from backend.services import github_skill_import as gsi

ADMIN = {"X-Admin-Token": "test-admin-secret-token-at-least-32-chars-long"}

FAKE_REPO = {
    "cooking/SKILL.md": b"---\nname: Cooking\ndescription: Cook things.\n---\nBody",
    "baking/SKILL.md": b"---\nname: Baking\n---\nBody",
}


@pytest.fixture(autouse=True)
def _admin_secret(monkeypatch):
    monkeypatch.setattr("backend.routers.admin.settings.ADMIN_PASSWORD", ADMIN["X-Admin-Token"])


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


@pytest.mark.asyncio
async def test_requires_admin_token(client: AsyncClient):
    assert (await client.get("/api/v1/admin/discover-skills")).status_code == 401
    bad = await client.post(
        "/api/v1/admin/discover-skills/import",
        json={"repo_url": "https://github.com/acme/skills"},
        headers={"X-Admin-Token": "wrong"},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_import_list_remove_round_trip(client: AsyncClient, monkeypatch):
    _fake_github(monkeypatch, FAKE_REPO)
    url = "https://github.com/acme/skills"

    imported = await client.post(
        "/api/v1/admin/discover-skills/import", json={"repo_url": url}, headers=ADMIN
    )
    assert imported.status_code == 200
    assert imported.json() == {
        "repo_url": url,
        "skills_found": 2,
        "created": 2,
        "updated": 0,
    }

    # The new skills appear in the public catalog, grouped under the repo here.
    listed = await client.get("/api/v1/admin/discover-skills", headers=ADMIN)
    repos = listed.json()["repos"]
    assert len(repos) == 1
    assert repos[0]["repo_url"] == url
    assert {s["title"] for s in repos[0]["skills"]} == {"Cooking", "Baking"}
    catalog = await client.get("/api/v1/discover/skills")
    assert {s["title"] for s in catalog.json()["skills"]} >= {"Cooking", "Baking"}

    # Re-import is idempotent: updates in place, nothing new created.
    again = await client.post(
        "/api/v1/admin/discover-skills/import", json={"repo_url": url}, headers=ADMIN
    )
    assert again.json()["created"] == 0
    assert again.json()["updated"] == 2

    removed = await client.post(
        "/api/v1/admin/discover-skills/remove", json={"repo_url": url}, headers=ADMIN
    )
    assert removed.json() == {"repo_url": url, "removed": 2}
    assert (await client.get("/api/v1/admin/discover-skills", headers=ADMIN)).json()["repos"] == []
    gone = await client.get("/api/v1/discover/skills")
    assert {s["title"] for s in gone.json()["skills"]}.isdisjoint({"Cooking", "Baking"})


@pytest.mark.asyncio
async def test_import_empty_repo_is_404(client: AsyncClient, monkeypatch):
    _fake_github(monkeypatch, {"README.md": b"no skills here"})
    resp = await client.post(
        "/api/v1/admin/discover-skills/import",
        json={"repo_url": "https://github.com/acme/empty"},
        headers=ADMIN,
    )
    assert resp.status_code == 404
