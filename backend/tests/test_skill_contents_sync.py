"""The skill-contents endpoints back `stash skills sync`: GET inlines a
workspace skill's full subtree (published or not), PUT replaces the folder's
contents with an uploaded file set. These lock in the replace semantics —
exact filenames kept, nesting from relative paths, no orphaned rows — and the
auth boundary (members only, write access to push)."""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _make_skill(client: AsyncClient, api_key: str) -> tuple[str, str]:
    """Returns (owner_user_id, folder_id) for a fresh unpublished skill."""
    ws = await client.post("/api/v1/workspaces", json={"name": "Sync ws"}, headers=_auth(api_key))
    owner_user_id = ws.json()["id"]
    folder = await client.post(
        f"/api/v1/workspaces/{owner_user_id}/folders",
        json={"name": "my-skill"},
        headers=_auth(api_key),
    )
    folder_id = folder.json()["id"]
    page = await client.post(
        f"/api/v1/workspaces/{owner_user_id}/pages/new",
        json={
            "name": "SKILL.md",
            "content": "---\nname: my-skill\n---\nv1",
            "folder_id": folder_id,
        },
        headers=_auth(api_key),
    )
    assert page.status_code == 201
    return owner_user_id, folder_id


@pytest.mark.asyncio
async def test_get_contents_inlines_unpublished_skill(client: AsyncClient):
    api_key = await _register(client)
    owner_user_id, folder_id = await _make_skill(client, api_key)

    resp = await client.get(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["folder_name"] == "my-skill"
    names = {p["name"] for p in body["contents"]["pages"]}
    assert names == {"SKILL.md"}

    # Members only — anonymous reads are for published slugs, not folders.
    anon = await client.get(f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents")
    assert anon.status_code in (401, 403)


@pytest.mark.asyncio
async def test_put_contents_replaces_subtree(client: AsyncClient, pool):
    api_key = await _register(client)
    owner_user_id, folder_id = await _make_skill(client, api_key)

    resp = await client.put(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        files=[
            ("files", ("SKILL.md", b"---\nname: my-skill\n---\nv2", "text/markdown")),
            ("files", ("references/guide.md", b"# guide", "text/markdown")),
        ],
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == 2

    got = await client.get(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        headers=_auth(api_key),
    )
    contents = got.json()["contents"]
    by_name = {p["name"]: p for p in contents["pages"]}
    assert by_name["SKILL.md"]["content_markdown"].endswith("v2")
    assert by_name["guide.md"]["folder_path"] == ["references"]

    # Replace again with a smaller set: the old nested page must be gone and
    # nothing may orphan into the workspace root (folder FKs are SET NULL).
    resp = await client.put(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        files=[("files", ("SKILL.md", b"v3", "text/markdown"))],
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    got = await client.get(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        headers=_auth(api_key),
    )
    assert {p["name"] for p in got.json()["contents"]["pages"]} == {"SKILL.md"}
    orphans = await pool.fetchval(
        "SELECT COUNT(*) FROM pages WHERE owner_user_id = $1 AND folder_id IS NULL",
        owner_user_id,
    )
    assert orphans == 0


@pytest.mark.asyncio
async def test_put_contents_requires_skill_md_and_membership(client: AsyncClient):
    api_key = await _register(client)
    owner_user_id, folder_id = await _make_skill(client, api_key)

    missing = await client.put(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        files=[("files", ("notes.md", b"no skill md", "text/markdown"))],
        headers=_auth(api_key),
    )
    assert missing.status_code == 400

    traversal = await client.put(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        files=[("files", ("../escape.md", b"x", "text/markdown"))],
        headers=_auth(api_key),
    )
    assert traversal.status_code == 400

    outsider_key = await _register(client)
    outsider = await client.put(
        f"/api/v1/workspaces/{owner_user_id}/skills/{folder_id}/contents",
        files=[("files", ("SKILL.md", b"hijack", "text/markdown"))],
        headers=_auth(outsider_key),
    )
    assert outsider.status_code == 403
