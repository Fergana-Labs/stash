"""Tests for folder-shaped skills.

A skill is a folder classified by a `skills` record — SKILL.md alone means
nothing. Two properties matter:

- MECE: classified skill subtrees are *moved* out of every Files surface
  (tree, sidebar, parent folder contents) and into the Skills area — never
  shown twice.
- Access is orthogonal: the record classifies; a public share on the folder
  is what grants READ on the whole subtree, and never write.
"""

import uuid

import pytest
from httpx import AsyncClient

from backend.services import (
    files_tree_service,
    permission_service,
    share_service,
    shared_skill_service,
)

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("folder_skill"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _scope(client: AsyncClient, api_key: str) -> str:
    resp = await client.get("/api/v1/users/me", headers=_auth(api_key))
    assert resp.status_code == 200
    return resp.json()["id"]


async def _folder(client, api_key, scope, name, parent_folder_id=None) -> str:
    body = {"name": name}
    if parent_folder_id:
        body["parent_folder_id"] = parent_folder_id
    resp = await client.post("/api/v1/me/folders", json=body, headers=_auth(api_key))
    assert resp.status_code == 201
    return resp.json()["id"]


async def _page(client, api_key, scope, name, folder_id=None, content="content") -> str:
    body = {"name": name, "content": content}
    if folder_id:
        body["folder_id"] = folder_id
    resp = await client.post("/api/v1/me/pages/new", json=body, headers=_auth(api_key))
    assert resp.status_code == 201
    return resp.json()["id"]


def _all_tree_folder_ids(node: dict) -> set[str]:
    ids = set()
    for folder in node["folders"]:
        ids.add(folder["id"])
        ids |= _all_tree_folder_ids(folder)
    return ids


# --- MECE: classified skill subtrees leave the Files surfaces ---


@pytest.mark.asyncio
async def test_skill_record_not_skill_md_classifies_folder(client: AsyncClient):
    """Classification is the skills record, not SKILL.md sniffing: a folder
    with a SKILL.md but no record stays in Files and off the skills list;
    creating the record moves the whole subtree to the Skills area, and
    deleting the record moves it back."""
    api_key, _ = await _register(client)
    scope = await _scope(client, api_key)

    docs = await _folder(client, api_key, scope, "Docs")
    skill_folder = await _folder(client, api_key, scope, "my-skill", parent_folder_id=docs)
    nested = await _folder(client, api_key, scope, "refs", parent_folder_id=skill_folder)
    skill_md = await _page(client, api_key, scope, "SKILL.md", folder_id=skill_folder)
    nested_page = await _page(client, api_key, scope, "notes", folder_id=nested)

    # SKILL.md alone does NOT classify: the folder stays on every Files
    # surface and off the skills list.
    tree = (await client.get("/api/v1/me/tree", headers=_auth(api_key))).json()
    assert skill_folder in _all_tree_folder_ids(tree)
    sidebar = (await client.get("/api/v1/me/sidebar", headers=_auth(api_key))).json()
    assert skill_folder in {f["id"] for f in sidebar["files"]["folders"]}
    assert skill_folder not in {s["folder_id"] for s in sidebar["skills"]}
    listed = (await client.get("/api/v1/me/skills", headers=_auth(api_key))).json()["skills"]
    assert skill_folder not in {s["folder_id"] for s in listed}

    # Creating the record classifies the folder.
    created = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": skill_folder, "title": "My skill"},
        headers=_auth(api_key),
    )
    assert created.status_code == 201
    skill_id = created.json()["id"]

    # /tree hides the whole skill subtree (the classified folder + descendants).
    tree = (await client.get("/api/v1/me/tree", headers=_auth(api_key))).json()
    tree_folder_ids = _all_tree_folder_ids(tree)
    assert docs in tree_folder_ids
    assert skill_folder not in tree_folder_ids
    assert nested not in tree_folder_ids

    # /sidebar files payload hides the subtree's folders and pages too.
    sidebar = (await client.get("/api/v1/me/sidebar", headers=_auth(api_key))).json()
    sidebar_folder_ids = {f["id"] for f in sidebar["files"]["folders"]}
    sidebar_page_ids = {p["id"] for p in sidebar["files"]["pages"]}
    assert docs in sidebar_folder_ids
    assert skill_folder not in sidebar_folder_ids
    assert nested not in sidebar_folder_ids
    assert skill_md not in sidebar_page_ids
    assert nested_page not in sidebar_page_ids
    # ...and the sidebar surfaces it as a skill instead.
    assert skill_folder in {s["folder_id"] for s in sidebar["skills"]}

    # The parent folder's contents skip the skill subfolder.
    docs_contents = (
        await client.get(f"/api/v1/me/folders/{docs}/contents", headers=_auth(api_key))
    ).json()
    assert [f["id"] for f in docs_contents["subfolders"]] == []

    # Opening the skill folder directly still works and is flagged as a skill.
    skill_contents = await client.get(
        f"/api/v1/me/folders/{skill_folder}/contents",
        headers=_auth(api_key),
    )
    assert skill_contents.status_code == 200
    body = skill_contents.json()
    assert body["folder"]["is_skill"] is True
    assert "SKILL.md" in [p["name"] for p in body["pages"]]
    assert nested in [f["id"] for f in body["subfolders"]]

    # Deleting the record declassifies: the folder rejoins the Files tree even
    # though its SKILL.md still exists.
    deleted = await client.delete(f"/api/v1/skills/{skill_id}", headers=_auth(api_key))
    assert deleted.status_code == 204
    tree_after = (await client.get("/api/v1/me/tree", headers=_auth(api_key))).json()
    assert skill_folder in _all_tree_folder_ids(tree_after)
    listed_after = (await client.get("/api/v1/me/skills", headers=_auth(api_key))).json()["skills"]
    assert skill_folder not in {s["folder_id"] for s in listed_after}


# --- Published skill = read grant on the whole folder subtree ---


async def _make_user(pool):
    return await pool.fetchval(
        "INSERT INTO users (name, display_name) VALUES ($1, $1) RETURNING id",
        unique_name("subtree"),
    )


async def _make_scope(pool, creator_id):
    return creator_id


async def _make_folder(pool, scope, created_by, name, parent_folder_id=None):
    return await pool.fetchval(
        "INSERT INTO folders (owner_user_id, parent_folder_id, name, created_by) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        scope,
        parent_folder_id,
        name,
        created_by,
    )


async def _make_page(pool, scope, created_by, folder_id, name="page"):
    return await pool.fetchval(
        "INSERT INTO pages (owner_user_id, folder_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, $3, 'body', $4) RETURNING id",
        scope,
        folder_id,
        name,
        created_by,
    )


@pytest.mark.asyncio
async def test_public_skill_folder_grants_subtree_read_never_write(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    root = await _make_folder(pool, scope, owner, "skill-root")
    mid = await _make_folder(pool, scope, owner, "mid", parent_folder_id=root)
    deep = await _make_folder(pool, scope, owner, "deep", parent_folder_id=mid)
    page = await _make_page(pool, scope, owner, deep, name="deep page")

    await shared_skill_service.create_skill_record(scope, owner, root, title="Subtree skill")

    # Classification alone grants nothing to outsiders.
    assert not await permission_service.check_access("page", page, stranger)

    await share_service.set_general_access(
        object_type="folder", object_id=root, access="public", owner_id=owner
    )

    # The public share grants READ on the whole subtree — anonymous included.
    assert await permission_service.check_access("page", page, stranger)
    assert await permission_service.check_access("page", page, None)
    assert await permission_service.check_access("folder", deep, stranger)
    # ...but never write.
    assert not await permission_service.check_access("page", page, stranger, require="write")


@pytest.mark.asyncio
async def test_unpublished_skill_folder_page_not_readable_by_stranger(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await _make_folder(pool, scope, owner, "private-skill")
    await _make_page(pool, scope, owner, folder, name="SKILL.md")
    page = await _make_page(pool, scope, owner, folder, name="secret")

    assert not await permission_service.check_access("page", page, stranger)
    assert not await permission_service.check_access("page", page, None)


# --- Session materialization ---


@pytest.mark.asyncio
async def test_materialize_session_creates_transcript_page_in_folder(client: AsyncClient):
    api_key, _ = await _register(client)
    scope = await _scope(client, api_key)

    pushed = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "tester",
            "event_type": "assistant_message",
            "content": "we fixed the auth bug",
            "session_id": "mat-sess-1",
        },
        headers=_auth(api_key),
    )
    assert pushed.status_code == 201

    skill_folder = await _folder(client, api_key, scope, "session-skill")
    await _page(client, api_key, scope, "SKILL.md", folder_id=skill_folder)

    materialized = await client.post(
        "/api/v1/me/sessions/mat-sess-1/materialize",
        json={"folder_id": skill_folder},
        headers=_auth(api_key),
    )
    assert materialized.status_code == 201, materialized.text
    page = materialized.json()
    assert page["folder_id"] == skill_folder
    assert page["name"] == "Session mat-sess-1.md"
    assert page["content_markdown"].startswith("# Session mat-sess-1")
    assert "we fixed the auth bug" in page["content_markdown"]


@pytest.mark.asyncio
async def test_rematerialize_session_replaces_snapshot_page_in_place(client: AsyncClient):
    """Materializing the same session twice must not pile up copies: the second
    run refreshes the existing snapshot page (same id, new content)."""
    api_key, register_body = await _register(client)
    scope = await _scope(client, api_key)

    async def _push_event(content: str):
        resp = await client.post(
            "/api/v1/me/sessions/events",
            json={
                "agent_name": "tester",
                "event_type": "assistant_message",
                "content": content,
                "session_id": "remat-sess-1",
            },
            headers=_auth(api_key),
        )
        assert resp.status_code == 201

    await _push_event("first finding")
    folder = await _folder(client, api_key, scope, "remat-skill")

    first = await client.post(
        "/api/v1/me/sessions/remat-sess-1/materialize",
        json={"folder_id": folder},
        headers=_auth(api_key),
    )
    assert first.status_code == 201, first.text
    first_page = first.json()
    assert "first finding" in first_page["content_markdown"]

    await _push_event("second finding")
    second = await client.post(
        "/api/v1/me/sessions/remat-sess-1/materialize",
        json={"folder_id": folder},
        headers=_auth(api_key),
    )
    assert second.status_code == 201, second.text
    second_page = second.json()

    # Same page, refreshed content, no duplicate.
    assert second_page["id"] == first_page["id"]
    assert "second finding" in second_page["content_markdown"]
    contents = (
        await client.get(f"/api/v1/me/folders/{folder}/contents", headers=_auth(api_key))
    ).json()
    session_pages = [p for p in contents["pages"] if p["name"] == "Session remat-sess-1.md"]
    assert len(session_pages) == 1

    # Snapshot pages are frozen: only re-snapshotting the origin may change them.
    with pytest.raises(ValueError, match="Snapshot pages cannot be edited"):
        await files_tree_service.update_page(
            uuid.UUID(first_page["id"]),
            uuid.UUID(scope),
            uuid.UUID(register_body["id"]),
            content="hand edit",
        )


@pytest.mark.asyncio
async def test_materialize_unknown_session_404(client: AsyncClient):
    api_key, _ = await _register(client)
    scope = await _scope(client, api_key)
    folder = await _folder(client, api_key, scope, "empty-skill")

    resp = await client.post(
        "/api/v1/me/sessions/no-such-session/materialize",
        json={"folder_id": folder},
        headers=_auth(api_key),
    )
    assert resp.status_code == 404


# --- Record lifecycle ---


@pytest.mark.asyncio
async def test_create_record_mints_skill_md_when_missing_and_rejects_double_create(
    client: AsyncClient,
):
    api_key, _ = await _register(client)
    scope = await _scope(client, api_key)
    folder = await _folder(client, api_key, scope, "bare-folder")

    created = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder, "title": "Minted skill"},
        headers=_auth(api_key),
    )
    assert created.status_code == 201, created.text
    assert created.json()["folder_id"] == folder

    # Classifying turned the bare folder into a skill by minting SKILL.md.
    contents = (
        await client.get(f"/api/v1/me/folders/{folder}/contents", headers=_auth(api_key))
    ).json()
    assert contents["folder"]["is_skill"] is True
    assert "SKILL.md" in [p["name"] for p in contents["pages"]]

    # The record is 1:1 with the folder — a second create must 400.
    again = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder, "title": "Minted skill"},
        headers=_auth(api_key),
    )
    assert again.status_code == 400
    assert "already a skill" in again.json()["detail"]


# --- Person-to-person sharing rides generic folder shares ---


async def _register_with_email(client: AsyncClient, email: str) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("folder_skill"), "password": "securepassword1", "email": email},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


@pytest.mark.asyncio
async def test_folder_share_grants_skill_read_and_lists_in_shared_skills(client: AsyncClient):
    """Replaces the retired skill-invite system: sharing a skill's FOLDER with a
    user grants subtree read, and GET /api/v1/me/shared-skills surfaces it
    (with the publish slug when the owner has also published)."""
    owner_key, _ = await _register(client)
    scope = await _scope(client, owner_key)
    skill_folder = await _folder(client, owner_key, scope, "partner-skill")
    await _page(
        client,
        owner_key,
        scope,
        "SKILL.md",
        folder_id=skill_folder,
        content="---\nname: Partner Playbook\ndescription: How we partner\n---\n\n# Go\n",
    )
    nested_page = await _page(
        client, owner_key, scope, "private plan", folder_id=skill_folder, content="private context"
    )
    published = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": skill_folder, "title": "Partner Playbook"},
        headers=_auth(owner_key),
    )
    assert published.status_code == 201
    slug = published.json()["slug"]

    recipient_key, _ = await _register_with_email(client, "skill-grantee@example.com")
    before = await client.get("/api/v1/me/shared-skills", headers=_auth(recipient_key))
    assert before.status_code == 200
    assert before.json()["skills"] == []

    shared = await client.post(
        "/api/v1/share",
        json={
            "object_type": "folder",
            "object_id": skill_folder,
            "email": "skill-grantee@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert shared.status_code == 200

    listed = await client.get("/api/v1/me/shared-skills", headers=_auth(recipient_key))
    assert listed.status_code == 200
    [skill] = listed.json()["skills"]
    assert skill["folder_id"] == skill_folder
    assert skill["name"] == "Partner Playbook"
    assert skill["description"] == "How we partner"
    assert skill["permission"] == "read"
    assert skill["slug"] == slug

    # The folder share grants subtree read of the skill's contents. The
    # recipient reaches the owner's page through the canonical object route.
    page_read = await client.get(f"/api/v1/pages/{nested_page}", headers=_auth(recipient_key))
    assert page_read.status_code == 200
    assert page_read.json()["content_markdown"] == "private context"
