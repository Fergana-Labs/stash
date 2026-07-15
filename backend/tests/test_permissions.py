"""Tests for Skill-mediated content access."""

import uuid

import pytest
from httpx import AsyncClient

from backend.services import (
    permission_service,
    session_folder_service,
    share_service,
    shared_skill_service,
)

from .conftest import unique_name


async def _make_user(pool, name=None):
    name = name or unique_name()
    row = await pool.fetchrow(
        "INSERT INTO users (name, display_name) VALUES ($1, $2) RETURNING id",
        name,
        name,
    )
    user_id = row["id"]
    await pool.execute(
        "INSERT INTO user_api_keys (user_id, key_hash, name) VALUES ($1, $2, 'test')",
        user_id,
        "hash_" + uuid.uuid4().hex,
    )
    return user_id


async def _register(client: AsyncClient, name: str | None = None) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": name or unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


async def _register_with_email(client: AsyncClient, email: str) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1", "email": email},
    )
    assert resp.status_code == 201
    body = resp.json()
    return body["api_key"], body


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _make_scope(pool, creator_id):
    return creator_id


async def _make_folder(pool, owner_user_id, created_by, name="folder", parent_folder_id=None):
    row = await pool.fetchrow(
        "INSERT INTO folders (owner_user_id, parent_folder_id, name, created_by) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        owner_user_id,
        parent_folder_id,
        name,
        created_by,
    )
    return row["id"]


async def _make_page(
    pool, owner_user_id, created_by, folder_id=None, name="page", content="content"
):
    row = await pool.fetchrow(
        "INSERT INTO pages (owner_user_id, folder_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        owner_user_id,
        folder_id,
        name,
        content,
        created_by,
    )
    return row["id"]


async def _make_session(pool, owner_user_id, created_by, session_id="session-1"):
    row = await pool.fetchrow(
        "INSERT INTO sessions (owner_user_id, session_id, agent_name, created_by) "
        "VALUES ($1, $2, 'codex', $3) RETURNING id",
        owner_user_id,
        session_id,
        created_by,
    )
    return row["id"]


async def _make_table(pool, owner_user_id, created_by, folder_id=None, name="table"):
    row = await pool.fetchrow(
        "INSERT INTO tables (owner_user_id, folder_id, name, created_by) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        owner_user_id,
        folder_id,
        name,
        created_by,
    )
    return row["id"]


async def _make_file(
    pool, owner_user_id, uploaded_by, folder_id=None, name="file.txt", content_type="text/plain"
):
    row = await pool.fetchrow(
        "INSERT INTO files "
        "(owner_user_id, folder_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, 12, $5, $6) RETURNING id",
        owner_user_id,
        folder_id,
        name,
        content_type,
        f"test/{uuid.uuid4().hex}.txt",
        uploaded_by,
    )
    return row["id"]


async def _make_history_event(
    pool,
    owner_user_id,
    created_by,
    session_id=None,
    content="hello",
    event_type="message",
):
    return await pool.fetchval(
        "INSERT INTO history_events "
        "(owner_user_id, created_by, agent_name, event_type, content, session_id) "
        "VALUES ($1, $2, 'agent', $3, $4, $5) RETURNING id",
        owner_user_id,
        created_by,
        event_type,
        content,
        session_id,
    )


# --- New model: private by default; owner + shares + publish record ---


async def _share(pool, scope_id, object_type, object_id, user_id, permission="read", by=None):
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1,$2,$3,'user',$4,$5,$6)",
        scope_id,
        object_type,
        object_id,
        user_id,
        permission,
        by or user_id,
    )


@pytest.mark.asyncio
async def test_owner_has_read_and_write(pool):
    owner = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    assert await permission_service.check_access("page", page, owner)
    assert await permission_service.check_access("page", page, owner, require="write")


@pytest.mark.asyncio
async def test_read_share_can_read_not_write(pool):
    owner = await _make_user(pool)
    viewer = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    await _share(pool, scope, "page", page, viewer, "read", by=owner)

    assert await permission_service.check_access("page", page, viewer)
    assert not await permission_service.check_access("page", page, viewer, require="write")


@pytest.mark.asyncio
async def test_stranger_denied_by_default(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    assert not await permission_service.check_access("page", page, stranger)
    assert not await permission_service.check_access("page", page, None)


@pytest.mark.asyncio
async def test_user_share_grants_read_not_write(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    await _share(pool, scope, "page", page, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    assert not await permission_service.check_access("page", page, friend, require="write")


@pytest.mark.asyncio
async def test_user_write_share_grants_write(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    await _share(pool, scope, "page", page, friend, "write", by=owner)
    assert await permission_service.check_access("page", page, friend, require="write")


@pytest.mark.asyncio
async def test_comment_tier_sits_between_read_and_write(pool):
    """read < comment < write: a read share can't comment; a comment share can
    comment but not write; a write share can do everything."""
    owner = await _make_user(pool)
    reader = await _make_user(pool)
    commenter = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    await _share(pool, scope, "page", page, reader, "read", by=owner)
    await _share(pool, scope, "page", page, commenter, "comment", by=owner)

    # read share: can read, cannot comment, cannot write.
    assert await permission_service.check_access("page", page, reader)
    assert not await permission_service.check_access("page", page, reader, require="comment")
    assert not await permission_service.check_access("page", page, reader, require="write")
    # comment share: can read + comment, not write.
    assert await permission_service.check_access("page", page, commenter, require="comment")
    assert not await permission_service.check_access("page", page, commenter, require="write")


@pytest.mark.asyncio
async def test_expired_share_grants_nothing(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by, expires_at) "
        "VALUES ($1,'page',$2,'user',$3,'write',$4, now() - interval '1 hour')",
        scope,
        page,
        friend,
        owner,
    )
    # Expired → no access, and absent from the readable predicate / with-me list.
    assert not await permission_service.check_access("page", page, friend)
    with_me = await share_service.list_shared_with_user(friend)
    assert all(item["object_id"] != str(page) for item in with_me)


@pytest.mark.asyncio
async def test_future_expiry_still_grants(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by, expires_at) "
        "VALUES ($1,'page',$2,'user',$3,'read',$4, now() + interval '1 day')",
        scope,
        page,
        friend,
        owner,
    )
    assert await permission_service.check_access("page", page, friend)


@pytest.mark.asyncio
async def test_folder_share_cascades_to_children(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await _make_folder(pool, scope, owner)
    page = await _make_page(pool, scope, owner, folder_id=folder)
    file_id = await _make_file(pool, scope, owner, folder_id=folder)
    table = await _make_table(pool, scope, owner, folder_id=folder)
    await _share(pool, scope, "folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    assert await permission_service.check_access("file", file_id, friend)
    assert await permission_service.check_access("table", table, friend)


@pytest.mark.asyncio
async def test_table_folder_share_cascades_and_write_inherits(pool):
    """A table inside a shared folder inherits the folder's grant — read from a
    read share, write from a write share — just like pages and files. A table
    at the scope root is unaffected by the folder share."""
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await _make_folder(pool, scope, owner)
    table = await _make_table(pool, scope, owner, folder_id=folder)
    root_table = await _make_table(pool, scope, owner, name="root-table")

    # Before any share the friend can't see either table.
    assert not await permission_service.check_access("table", table, friend)

    await _share(pool, scope, "folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("table", table, friend)
    # Read share is not a write grant, and the root table is outside the folder.
    assert not await permission_service.check_access("table", table, friend, require="write")
    assert not await permission_service.check_access("table", root_table, friend)

    # Upgrading the folder share to write cascades write to the table.
    await pool.execute(
        "UPDATE shares SET permission='write' WHERE object_type='folder' "
        "AND object_id=$1 AND principal_id=$2",
        folder,
        friend,
    )
    assert await permission_service.check_access("table", table, friend, require="write")


@pytest.mark.asyncio
async def test_table_share_by_email_grants_direct_read(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    table = await _make_table(pool, scope, owner, name="prospects")
    await pool.execute(
        "UPDATE users SET email = 'friend@example.com' WHERE id = $1",
        friend,
    )

    await share_service.share_with_user_by_email(
        object_type="table",
        object_id=table,
        email="friend@example.com",
        permission="read",
        owner_id=owner,
    )

    assert await permission_service.check_access("table", table, friend)
    assert not await permission_service.check_access(
        "table",
        table,
        friend,
        require="write",
    )


@pytest.mark.asyncio
async def test_published_skill_grants_read_only(pool):
    """A publish record's existence makes the skill folder publicly readable —
    stranger and anonymous alike — but is never a write grant."""
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await _make_folder(pool, scope, owner, name="public-skill")
    page = await _make_page(pool, scope, owner, folder_id=folder)
    await _make_page(
        pool,
        scope,
        owner,
        folder_id=folder,
        name="SKILL.md",
        content="---\nname: Public Skill\ndescription: Test public access.\n---\n",
    )
    await shared_skill_service.publish_folder(scope, owner, folder)
    assert await permission_service.check_access("page", page, stranger)
    assert await permission_service.check_access("page", page, None)
    assert not await permission_service.check_access("page", page, stranger, require="write")


@pytest.mark.asyncio
async def test_public_session_folder_grants_read_only(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await session_folder_service.create_folder(
        scope,
        "Public Sessions",
        public_permission="read",
    )
    folder_id = uuid.UUID(folder["id"])

    assert await permission_service.check_access("session_folder", folder_id, stranger)
    assert await permission_service.check_access("session_folder", folder_id, None)
    assert not await permission_service.check_access(
        "session_folder", folder_id, stranger, require="write"
    )
    assert not await permission_service.check_access(
        "session_folder", folder_id, None, require="write"
    )


@pytest.mark.asyncio
async def test_skill_folder_share_grants_friend_read_of_nested_contents(pool):
    """Person-to-person skill access rides generic folder shares: an unpublished
    skill folder shared with a friend grants them read of the nested contents
    (read share, so no write), while strangers stay locked out."""
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await _make_folder(pool, scope, owner, name="private-skill")
    await _make_page(pool, scope, owner, folder_id=folder, name="SKILL.md")
    page = await _make_page(pool, scope, owner, folder_id=folder)
    await _share(pool, scope, "folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    assert not await permission_service.check_access("page", page, friend, require="write")
    assert not await permission_service.check_access("page", page, stranger)


@pytest.mark.asyncio
async def test_share_then_unshare_revokes(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    page = await _make_page(pool, scope, owner)
    await _share(pool, scope, "page", page, friend, "read", by=owner)
    assert await permission_service.check_access("page", page, friend)
    await pool.execute(
        "DELETE FROM shares WHERE object_type='page' AND object_id=$1 AND principal_id=$2",
        page,
        friend,
    )
    assert not await permission_service.check_access("page", page, friend)


@pytest.mark.asyncio
async def test_session_folder_share_cascades_to_sessions(pool):
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await pool.fetchval(
        "INSERT INTO session_folders (owner_user_id, name, slug) "
        "VALUES ($1, 'launch', 'launch-' || left(replace(gen_random_uuid()::text, '-', ''), 8)) "
        "RETURNING id",
        scope,
    )
    session_row = await _make_session(pool, scope, owner, session_id="s-folder-1")
    await pool.execute(
        "UPDATE sessions SET session_folder_id = $2 WHERE id = $1", session_row, folder
    )
    # Not shared yet → friend denied.
    assert not await permission_service.check_access("session", session_row, friend)
    # Share the folder → cascades to the session.
    await _share(pool, scope, "session_folder", folder, friend, "read", by=owner)
    assert await permission_service.check_access("session", session_row, friend)


@pytest.mark.asyncio
async def test_share_by_email_grants_page_read_over_http(client: AsyncClient, pool):
    """The primary collaboration path, end-to-end through the REST API: a page
    is private to its owner until shared by email; the grantee (not the owner)
    then reads it, and a stranger still cannot.

    Regression for the single-item read endpoints gating on
    ownership and so ignoring shares."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "private roadmap"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    grantee_key, grantee = await _register(client)
    await pool.execute(
        "UPDATE users SET email = 'grantee@example.com' WHERE id = $1", grantee["id"]
    )
    stranger_key, _ = await _register(client)

    # Cross-user reads of a specific object go through the canonical route,
    # which resolves by id + check_access; the owner can use it too.
    page_url = f"/api/v1/pages/{page_id}"
    assert (await client.get(page_url, headers=_auth(owner_key))).status_code == 200
    # Private before any share.
    assert (await client.get(page_url, headers=_auth(grantee_key))).status_code == 404

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "grantee@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    # The share grants the other user read access; the stranger is still denied.
    assert (await client.get(page_url, headers=_auth(grantee_key))).status_code == 200
    assert (await client.get(page_url, headers=_auth(stranger_key))).status_code == 404


@pytest.mark.asyncio
async def test_unshared_file_read_returns_not_found_over_http(client: AsyncClient, pool):
    """A stranger reading an unshared file via the canonical route gets 404, not
    403: an unscoped single-object lookup must not confirm a file the caller
    can't read exists. A genuinely missing id is also 404, indistinguishable."""
    owner_key, owner = await _register(client)
    scope = (await client.get("/api/v1/users/me", headers=_auth(owner_key))).json()["id"]
    file_id = await _make_file(pool, uuid.UUID(scope), uuid.UUID(owner["id"]))
    stranger_key, _ = await _register(client)

    denied = await client.get(f"/api/v1/files/{file_id}", headers=_auth(stranger_key))
    assert denied.status_code == 404
    assert denied.json()["detail"] == "File not found"

    missing = await client.get(
        f"/api/v1/files/{uuid.uuid4()}",
        headers=_auth(owner_key),
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "File not found"


@pytest.mark.asyncio
async def test_folder_share_by_email_cascades_read_to_children_over_http(client: AsyncClient):
    """A folder share must cascade read to the folder's nested contents for a
    non-owner: end-to-end over the share-by-email HTTP path, the grantee can't
    reach a child page until the parent folder is shared, then reads it via the
    canonical object route. Guards the cascade against gating on ownership."""
    owner_key, _ = await _register(client)
    folder_id = (
        await client.post(
            "/api/v1/me/folders",
            json={"name": "Specs"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"folder_id": folder_id, "name": "Roadmap", "content": "Q3 plan"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    grantee_key, _ = await _register_with_email(client, "folder-grantee@example.com")

    # Cross-user reads of the child go through the canonical object route.
    page_url = f"/api/v1/pages/{page_id}"
    assert (await client.get(page_url, headers=_auth(grantee_key))).status_code == 404

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "folder",
            "object_id": folder_id,
            "email": "folder-grantee@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    # The folder share cascades read to the contained page.
    child = await client.get(page_url, headers=_auth(grantee_key))
    assert child.status_code == 200
    assert child.json()["id"] == page_id


@pytest.mark.asyncio
async def test_write_share_by_email_grants_non_owner_write_over_http(
    client: AsyncClient,
):
    """A write share, set up end-to-end over the share-by-email HTTP path, is a
    real write grant on the object for a non-owner: the grantee can both read
    the page (canonical route) and passes the write check, while a stranger
    can do neither. Ownership is not a prerequisite for a user share."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Draft", "content": "before"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    writer_key, writer = await _register_with_email(client, "writer@example.com")
    stranger_key, stranger = await _register(client)

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "writer@example.com",
            "permission": "write",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    # The write-share grantee can read the page via the canonical object route
    # and holds a write grant on it; the stranger has neither.
    assert (
        await client.get(f"/api/v1/pages/{page_id}", headers=_auth(writer_key))
    ).status_code == 200
    assert await permission_service.check_access(
        "page", uuid.UUID(page_id), uuid.UUID(writer["id"]), require="write"
    )
    assert (
        await client.get(f"/api/v1/pages/{page_id}", headers=_auth(stranger_key))
    ).status_code == 404
    assert not await permission_service.check_access(
        "page", uuid.UUID(page_id), uuid.UUID(stranger["id"]), require="write"
    )


@pytest.mark.asyncio
async def test_write_share_grantee_cannot_reshare_page_over_http(
    client: AsyncClient,
    pool,
):
    """Only the owner may share an object. A user who was
    granted write access via a share cannot re-share it onward."""
    owner_key, owner = await _register(client)
    writer_key, writer = await _register(client)
    scope = (await client.get("/api/v1/users/me", headers=_auth(owner_key))).json()["id"]
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Spec", "content": "confidential"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    await _share(
        pool,
        uuid.UUID(scope),
        "page",
        uuid.UUID(page_id),
        uuid.UUID(writer["id"]),
        "write",
        by=uuid.UUID(owner["id"]),
    )

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "external@example.com",
            "permission": "read",
        },
        headers=_auth(writer_key),
    )

    assert share.status_code == 404


@pytest.mark.asyncio
async def test_non_owner_cannot_publish_skill_folder(
    client: AsyncClient,
    pool,
):
    """Only the owner may publish their own folder as a skill. /me/skills acts
    purely on the caller's own scope, so a write-share grantee can't even name
    the owner's folder — it isn't in their scope, so the publish request fails."""
    owner_key, owner = await _register(client)
    writer_key, writer = await _register(client)
    scope = (await client.get("/api/v1/users/me", headers=_auth(owner_key))).json()["id"]
    folder_id = (
        await client.post(
            "/api/v1/me/folders",
            json={"name": "Internal Skill"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    await _share(
        pool,
        uuid.UUID(scope),
        "folder",
        uuid.UUID(folder_id),
        uuid.UUID(writer["id"]),
        "write",
        by=uuid.UUID(owner["id"]),
    )

    create = await client.post(
        "/api/v1/me/skills",
        json={
            "folder_id": folder_id,
            "title": "Internal Skill",
        },
        headers=_auth(writer_key),
    )

    assert create.status_code == 400
    assert create.json()["detail"] == "Folder not found in this scope"


@pytest.mark.asyncio
async def test_skill_owner_can_edit_published_skill_metadata(client: AsyncClient):
    owner_key, _ = await _register(client)
    folder_id = (
        await client.post(
            "/api/v1/me/folders",
            json={"name": "Handbook"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    skill_page = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": "SKILL.md",
            "folder_id": folder_id,
            "content": "---\nname: Handbook\ndescription: Team handbook.\n---\n",
        },
        headers=_auth(owner_key),
    )
    assert skill_page.status_code == 201
    skill_id = (
        await client.post(
            "/api/v1/me/skills",
            json={"folder_id": folder_id},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    rename = await client.patch(
        f"/api/v1/skills/{skill_id}",
        json={"title": "Handbook v2"},
        headers=_auth(owner_key),
    )

    assert rename.status_code == 200
    assert rename.json()["title"] == "Handbook v2"


@pytest.mark.asyncio
async def test_public_write_session_folder_requests_are_rejected(client: AsyncClient):
    owner_key, _ = await _register(client)

    create = await client.post(
        "/api/v1/me/session-folders",
        json={"name": "Editable sessions", "public_permission": "write"},
        headers=_auth(owner_key),
    )

    assert create.status_code == 422


@pytest.mark.asyncio
async def test_session_folder_share_by_email_lists_for_non_recipient(client: AsyncClient):
    owner_key, _ = await _register(client)
    folder_id = (
        await client.post(
            "/api/v1/me/session-folders",
            json={"name": "Deploys"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    session = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "deploy-1", "agent_name": "codex"},
        headers=_auth(owner_key),
    )
    assert session.status_code == 201
    assigned = await client.post(
        "/api/v1/me/session-folders/assign",
        json={"session_row_ids": [session.json()["id"]], "folder_id": folder_id},
        headers=_auth(owner_key),
    )
    assert assigned.status_code == 200

    grantee_key, _ = await _register_with_email(client, "session-folder-grantee@example.com")
    # Another user sees this user's session folder only once it's shared with
    # them — it surfaces on their "Shared with me" list, not in their own scope.
    before = await client.get("/api/v1/share/with-me", headers=_auth(grantee_key))
    assert before.status_code == 200
    assert folder_id not in {i["object_id"] for i in before.json()["items"]}

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "session_folder",
            "object_id": folder_id,
            "email": "session-folder-grantee@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    after = await client.get("/api/v1/share/with-me", headers=_auth(grantee_key))
    assert after.status_code == 200
    shared = [i for i in after.json()["items"] if i["object_id"] == folder_id]
    assert len(shared) == 1
    assert shared[0]["object_type"] == "session_folder"
    assert shared[0]["name"] == "Deploys"
    assert shared[0]["permission"] == "read"

    # The grantee can enumerate the folder's sessions via the shared route.
    sessions = await client.get(
        f"/api/v1/share/session-folders/{folder_id}/sessions",
        headers=_auth(grantee_key),
    )
    assert sessions.status_code == 200
    assert len(sessions.json()["sessions"]) == 1


@pytest.mark.asyncio
async def test_session_folder_write_access_cannot_manage_folder(client: AsyncClient):
    owner_key, _ = await _register(client)
    stranger_key, _ = await _register(client)
    writer_key, _ = await _register_with_email(client, "session-folder-writer@example.com")
    public_folder_id = (
        await client.post(
            "/api/v1/me/session-folders",
            json={"name": "Public Read", "public_permission": "read"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    shared_folder_id = (
        await client.post(
            "/api/v1/me/session-folders",
            json={"name": "Shared Write"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "session_folder",
            "object_id": shared_folder_id,
            "email": "session-folder-writer@example.com",
            "permission": "write",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200

    public_update = await client.patch(
        f"/api/v1/me/session-folders/{public_folder_id}",
        json={"name": "Renamed"},
        headers=_auth(stranger_key),
    )
    shared_delete = await client.delete(
        f"/api/v1/me/session-folders/{shared_folder_id}",
        headers=_auth(writer_key),
    )

    assert public_update.status_code == 404
    assert shared_delete.status_code == 404


@pytest.mark.asyncio
async def test_session_folder_assign_rejects_cross_scope_ids(client: AsyncClient):
    first_key, _ = await _register(client)
    second_key, _ = await _register(client)
    second_folder_id = (
        await client.post(
            "/api/v1/me/session-folders",
            json={"name": "Other Scope"},
            headers=_auth(second_key),
        )
    ).json()["id"]
    direct_upsert = await client.post(
        "/api/v1/me/sessions",
        json={
            "session_id": "cross-scope-direct",
            "agent_name": "codex",
            "session_folder_id": second_folder_id,
        },
        headers=_auth(first_key),
    )
    session = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "cross-scope-1", "agent_name": "codex"},
        headers=_auth(first_key),
    )
    assert session.status_code == 201

    assign = await client.post(
        "/api/v1/me/session-folders/assign",
        json={"session_row_ids": [session.json()["id"]], "folder_id": second_folder_id},
        headers=_auth(first_key),
    )

    assert direct_upsert.status_code == 404
    assert assign.status_code == 404


@pytest.mark.asyncio
async def test_session_folder_assign_batch_is_all_or_nothing(client: AsyncClient, pool):
    # A 404 on a mixed batch must mean nothing moved — otherwise the client's
    # view and the server state silently diverge.
    owner_key, _ = await _register(client)
    folder_id = (
        await client.post(
            "/api/v1/me/session-folders",
            json={"name": "Deploys"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    session = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "batch-1", "agent_name": "codex"},
        headers=_auth(owner_key),
    )
    assert session.status_code == 201
    valid_id = session.json()["id"]
    before = await pool.fetchrow(
        "SELECT session_folder_id FROM sessions WHERE id = $1", uuid.UUID(valid_id)
    )

    assign = await client.post(
        "/api/v1/me/session-folders/assign",
        json={"session_row_ids": [valid_id, str(uuid.uuid4())], "folder_id": folder_id},
        headers=_auth(owner_key),
    )

    assert assign.status_code == 404
    after = await pool.fetchrow(
        "SELECT session_folder_id FROM sessions WHERE id = $1", uuid.UUID(valid_id)
    )
    assert after["session_folder_id"] == before["session_folder_id"]


@pytest.mark.asyncio
async def test_share_by_email_pending_invite_converts_on_signup(client: AsyncClient):
    """Sharing to an email with no account yet records a pending invite that
    becomes a real share when that person signs up with the email."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Spec", "content": "secret spec"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    # Share to an email that has no user — recorded as pending, not 404.
    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "newcomer@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200
    assert share.json()["ok"] is True

    # The owner sees it listed as a pending invite.
    listing = await client.get(
        f"/api/v1/share?object_type=page&object_id={page_id}", headers=_auth(owner_key)
    )
    pending = [s for s in listing.json()["shares"] if s["pending"]]
    assert [s["email"] for s in pending] == ["newcomer@example.com"]

    # The newcomer signs up with that email → invite converts → they can read.
    newcomer_key, _ = await _register_with_email(client, "newcomer@example.com")
    # The newcomer reads someone else's shared page via the canonical route.
    page_url = f"/api/v1/pages/{page_id}"
    assert (await client.get(page_url, headers=_auth(newcomer_key))).status_code == 200

    # The pending invite is gone; it's now a real (non-pending) share.
    after = await client.get(
        f"/api/v1/share?object_type=page&object_id={page_id}", headers=_auth(owner_key)
    )
    rows = after.json()["shares"]
    assert all(not s["pending"] for s in rows)
    assert any(s["email"] == "newcomer@example.com" for s in rows)


@pytest.mark.asyncio
async def test_share_response_does_not_reveal_account_existence(client: AsyncClient):
    """The share response must be identical for known and unknown emails —
    a per-branch difference would let any owner probe which
    addresses have Stash accounts (a user-enumeration oracle)."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Spec", "content": "secret spec"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    await _register_with_email(client, "has-account@example.com")

    async def _share(email: str):
        return await client.post(
            "/api/v1/share",
            json={"object_type": "page", "object_id": page_id, "email": email},
            headers=_auth(owner_key),
        )

    known = await _share("has-account@example.com")
    unknown = await _share("no-account@example.com")

    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == {"ok": True, "email": "has-account@example.com"}
    assert unknown.json() == {"ok": True, "email": "no-account@example.com"}


@pytest.mark.asyncio
async def test_revoked_pending_share_invite_does_not_convert_on_signup(client: AsyncClient):
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Spec", "content": "secret spec"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "revoked-newcomer@example.com",
            "permission": "read",
        },
        headers=_auth(owner_key),
    )
    revoked = await client.request(
        "DELETE",
        "/api/v1/share/invite",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "REVOKED-NEWCOMER@example.com",
        },
        headers=_auth(owner_key),
    )
    listing = await client.get(
        f"/api/v1/share?object_type=page&object_id={page_id}",
        headers=_auth(owner_key),
    )
    newcomer_key, _ = await _register_with_email(
        client,
        "revoked-newcomer@example.com",
    )

    assert share.status_code == 200
    assert share.json()["ok"] is True
    assert revoked.status_code == 200
    assert listing.status_code == 200
    assert listing.json()["shares"] == []
    assert (
        await client.get(
            f"/api/v1/me/pages/{page_id}",
            headers=_auth(newcomer_key),
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_expired_pending_share_invite_does_not_convert_on_signup(client: AsyncClient, pool):
    """A time-bounded invite must not grant anything if the recipient signs up
    after the expiry — otherwise an expired invite would silently become
    permanent access."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Spec", "content": "secret spec"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "late-newcomer@example.com",
            "permission": "read",
            "expires_at": "2020-01-01T00:00:00Z",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200
    assert share.json()["ok"] is True

    newcomer_key, _ = await _register_with_email(client, "late-newcomer@example.com")

    assert (
        await client.get(
            f"/api/v1/pages/{page_id}",
            headers=_auth(newcomer_key),
        )
    ).status_code == 404
    # The expired invite is dropped, not left around to convert later.
    remaining = await pool.fetchval(
        "SELECT count(*) FROM share_invites WHERE lower(email) = 'late-newcomer@example.com'"
    )
    assert remaining == 0


@pytest.mark.asyncio
async def test_converted_share_keeps_invite_expiry(client: AsyncClient, pool):
    """When a pending invite converts on signup, the resulting share carries
    the invite's expires_at — conversion must not upgrade a time-bounded grant
    to a permanent one."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Spec", "content": "secret spec"},
            headers=_auth(owner_key),
        )
    ).json()["id"]

    share = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": page_id,
            "email": "timed-newcomer@example.com",
            "permission": "read",
            "expires_at": "2099-01-01T00:00:00Z",
        },
        headers=_auth(owner_key),
    )
    assert share.status_code == 200
    assert share.json()["ok"] is True

    newcomer_key, newcomer = await _register_with_email(client, "timed-newcomer@example.com")

    assert (
        await client.get(
            f"/api/v1/pages/{page_id}",
            headers=_auth(newcomer_key),
        )
    ).status_code == 200
    expires_at = await pool.fetchval(
        "SELECT expires_at FROM shares WHERE object_type = 'page' AND object_id = $1 "
        "AND principal_type = 'user' AND principal_id = $2",
        uuid.UUID(page_id),
        uuid.UUID(newcomer["id"]),
    )
    assert expires_at is not None
    assert expires_at.year == 2099


@pytest.mark.asyncio
async def test_shared_with_me_lists_incoming_not_outgoing(pool):
    from backend.services import share_service

    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    folder = await _make_folder(pool, scope, owner, name="Shared Folder")
    await _share(pool, scope, "folder", folder, friend, "write", by=owner)

    items = await share_service.list_shared_with_user(friend)
    match = [i for i in items if i["object_id"] == str(folder)]
    assert len(match) == 1
    assert match[0]["object_type"] == "folder"
    assert match[0]["name"] == "Shared Folder"
    assert match[0]["permission"] == "write"
    assert match[0]["owner_user_id"] == str(scope)
    # The owner is on the giving end — nothing is shared *with* them.
    assert await share_service.list_shared_with_user(owner) == []


@pytest.mark.asyncio
async def test_shared_session_folder_sessions_gated_on_share(pool):
    from fastapi import HTTPException

    from backend.services import share_service

    owner = await _make_user(pool)
    friend = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)
    sf = await pool.fetchval(
        "INSERT INTO session_folders (owner_user_id, name, slug) "
        "VALUES ($1, 'SF', 'sf-' || left(replace(gen_random_uuid()::text, '-', ''), 8)) "
        "RETURNING id",
        scope,
    )
    session_row = await _make_session(pool, scope, owner, session_id="shared-sess-1")
    await pool.execute("UPDATE sessions SET session_folder_id = $2 WHERE id = $1", session_row, sf)
    await _share(pool, scope, "session_folder", sf, friend, "read", by=owner)

    rows = await share_service.list_shared_session_folder_sessions(sf, friend)
    assert [r["id"] for r in rows] == [str(session_row)]

    # A stranger with no share is denied.
    with pytest.raises(HTTPException):
        await share_service.list_shared_session_folder_sessions(sf, stranger)


@pytest.mark.asyncio
async def test_session_list_does_not_leak_unshared_sessions(pool):
    """Regression: sharing a single object with someone must NOT expose all of
    your sessions. `readable_session_event_condition` gates each session on a
    real share — not merely on the viewer appearing in the accessible-scope
    prefilter, which a single page share already widens to include the owner."""
    from backend.services import memory_service

    owner = await _make_user(pool)
    friend = await _make_user(pool)
    scope = await _make_scope(pool, owner)

    session_row = await _make_session(pool, scope, owner, session_id="secret-sess")
    await _make_history_event(
        pool, scope, owner, session_id="secret-sess", content="secret transcript"
    )

    # Nothing shared yet: friend sees none of the owner's sessions.
    assert await memory_service.list_scope_sessions(scope, friend) == []

    # Sharing an UNRELATED page widens friend's accessible-scope prefilter to
    # include the owner — but must still not surface the owner's sessions.
    page = await _make_page(pool, scope, owner)
    await _share(pool, scope, "page", page, friend, "read", by=owner)
    assert await memory_service.list_scope_sessions(scope, friend) == []

    # The owner always sees their own session; sharing the session itself is
    # what surfaces it to the friend.
    owner_rows = await memory_service.list_scope_sessions(scope, owner)
    assert [r["session_id"] for r in owner_rows] == ["secret-sess"]

    await _share(pool, scope, "session", session_row, friend, "read", by=owner)
    friend_rows = await memory_service.list_scope_sessions(scope, friend)
    assert [r["session_id"] for r in friend_rows] == ["secret-sess"]


@pytest.mark.asyncio
async def test_overview_counts_span_shared_not_unshared(pool):
    """The "Your brain" vitals (analytics_service.get_overview_counts) span the
    user's own content plus content shared with them — but a share only surfaces
    the specific shared rows, never the whole sharing scope, and an unrelated
    user sees nothing. Guards the widened owned∪shared prefilter against leaks."""
    from backend.services import analytics_service

    owner = await _make_user(pool)
    friend = await _make_user(pool)  # gets one folder shared
    stranger = await _make_user(pool)  # gets nothing
    scope = await _make_scope(pool, owner)  # friend/stranger don't own this scope
    folder = await _make_folder(pool, scope, owner)
    await _make_page(pool, scope, owner, folder_id=folder, name="shared-page")
    await _make_page(pool, scope, owner, name="private-root-page")
    await _share(pool, scope, "folder", folder, friend, "read", by=owner)

    owner_counts = await analytics_service.get_overview_counts(owner)
    friend_counts = await analytics_service.get_overview_counts(friend)
    stranger_counts = await analytics_service.get_overview_counts(stranger)

    # Owner sees both of its pages; friend sees only the page in the shared
    # folder (not the un-shared root page); stranger sees neither.
    assert owner_counts["pages"] >= 2
    assert friend_counts["pages"] == 1
    assert stranger_counts["pages"] == 0


_PREDICATE_TABLE = {
    "folder": "folders",
    "page": "pages",
    "file": "files",
    "table": "tables",
    "session": "sessions",
}


async def _predicate_says(pool, object_type, object_id, user_id, require):
    """Run readable_content_condition as a WHERE against the single row — the SQL
    shape of the same question check_access answers as a boolean."""
    predicate = permission_service.readable_content_condition(object_type, "obj", 2, require)
    table = _PREDICATE_TABLE[object_type]
    return bool(
        await pool.fetchval(
            f"SELECT EXISTS (SELECT 1 FROM {table} obj WHERE obj.id = $1 AND {predicate})",
            object_id,
            user_id,
        )
    )


@pytest.mark.asyncio
async def test_predicate_and_check_access_agree(pool):
    """Keystone anti-drift guard: the SQL predicate (run as a WHERE) and the
    check_access boolean must return the SAME verdict for every resource type,
    grant, viewer, and level. They are two shapes of one rule; if they ever
    disagree, the rule has been forked — which is exactly the bug this refactor
    removes."""
    owner = await _make_user(pool)
    friend = await _make_user(pool)
    stranger = await _make_user(pool)
    scope = await _make_scope(pool, owner)

    folder = await _make_folder(pool, scope, owner)
    page = await _make_page(pool, scope, owner, folder_id=folder)
    fil = await _make_file(pool, scope, owner, folder_id=folder)
    tbl = await _make_table(pool, scope, owner, folder_id=folder)
    sess = await _make_session(pool, scope, owner, session_id="equiv-sess")

    # A read-share of the folder cascades to its page/file/table; the session is
    # shared directly. Exercises owner, share-via-ancestor, direct share, denial.
    await _share(pool, scope, "folder", folder, friend, "read", by=owner)
    await _share(pool, scope, "session", sess, friend, "read", by=owner)

    objects = [
        ("folder", folder),
        ("page", page),
        ("file", fil),
        ("table", tbl),
        ("session", sess),
    ]
    for object_type, object_id in objects:
        for viewer in (owner, friend, stranger, None):
            for require in ("read", "comment", "write"):
                boolean = await permission_service.check_access(
                    object_type, object_id, viewer, require=require
                )
                predicate = await _predicate_says(pool, object_type, object_id, viewer, require)
                assert boolean == predicate, (
                    f"DRIFT {object_type} viewer={viewer} require={require}: "
                    f"boolean={boolean} predicate={predicate}"
                )

    # Published-skill folder: stranger and anonymous get READ (never write), and
    # the predicate must agree. This is the public-read branch the refactor folded
    # into the one predicate, so it gets an explicit equivalence check.
    pub_folder = await _make_folder(pool, scope, owner, name="pub-skill")
    pub_page = await _make_page(pool, scope, owner, folder_id=pub_folder)
    await _make_page(
        pool,
        scope,
        owner,
        folder_id=pub_folder,
        name="SKILL.md",
        content="---\nname: Pub\ndescription: Test public access.\n---\n",
    )
    await shared_skill_service.publish_folder(scope, owner, pub_folder)
    for viewer in (stranger, None):
        for require in ("read", "write"):
            boolean = await permission_service.check_access(
                "page", pub_page, viewer, require=require
            )
            predicate = await _predicate_says(pool, "page", pub_page, viewer, require)
            assert boolean == predicate
            assert boolean is (require == "read")


@pytest.mark.asyncio
async def test_session_folder_owner_reads_sessions_they_do_not_own(pool):
    """A session-folder owner can READ every session filed under their folder —
    even sessions owned by someone else — and only at read level. Regression
    guard: the unified predicate must keep the folder-owner grant that the old
    _session_folder_open provided. (Equivalence alone can't catch this: predicate
    and boolean now agree by construction, so this asserts the actual decision.)"""
    folder_owner = await _make_user(pool)
    session_owner = await _make_user(pool)
    stranger = await _make_user(pool)
    folder = await pool.fetchval(
        "INSERT INTO session_folders (owner_user_id, name, slug) "
        "VALUES ($1, 'shared', 'shared-' || left(replace(gen_random_uuid()::text, '-', ''), 8)) "
        "RETURNING id",
        folder_owner,
    )
    session_row = await _make_session(pool, session_owner, session_owner, session_id="sf-owner-1")
    await pool.execute(
        "UPDATE sessions SET session_folder_id = $2 WHERE id = $1", session_row, folder
    )

    # Folder owner reads a session they don't own; stranger cannot.
    assert await permission_service.check_access("session", session_row, folder_owner)
    assert not await permission_service.check_access("session", session_row, stranger)
    # The grant is read-only — folder ownership confers no write.
    assert not await permission_service.check_access(
        "session", session_row, folder_owner, require="write"
    )
    # Predicate and boolean agree on every viewer for this scenario.
    for viewer in (folder_owner, session_owner, stranger):
        boolean = await permission_service.check_access("session", session_row, viewer)
        predicate = await _predicate_says(pool, "session", session_row, viewer, "read")
        assert boolean == predicate


# --- Per-object public link ("anyone with the link", read < comment < write) ---


async def _set_public(pool, table, object_id, permission):
    await pool.execute(
        f"UPDATE {table} SET public_permission = $1 WHERE id = $2", permission, object_id
    )


@pytest.mark.asyncio
async def test_public_read_link_grants_stranger_and_anonymous(pool):
    """A read link must let anyone — logged in or not — read but never write."""
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    page = await _make_page(pool, owner, owner)
    await _set_public(pool, "pages", page, "read")

    assert await permission_service.check_access("page", page, stranger)
    assert await permission_service.check_access("page", page, None)
    assert not await permission_service.check_access("page", page, stranger, require="write")
    assert not await permission_service.check_access("page", page, None, require="comment")


@pytest.mark.asyncio
async def test_public_comment_link_grants_comment_not_write(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    page = await _make_page(pool, owner, owner)
    await _set_public(pool, "pages", page, "comment")

    assert await permission_service.check_access("page", page, stranger, require="read")
    assert await permission_service.check_access("page", page, stranger, require="comment")
    assert not await permission_service.check_access("page", page, stranger, require="write")


@pytest.mark.asyncio
async def test_public_write_link_grants_every_level(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    page = await _make_page(pool, owner, owner)
    await _set_public(pool, "pages", page, "write")

    for require in ("read", "comment", "write"):
        assert await permission_service.check_access("page", page, stranger, require=require)


@pytest.mark.asyncio
async def test_public_folder_cascades_to_contents(pool):
    """A public folder grants its level to descendant pages/files/tables — the
    same cascade a folder share gets."""
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    folder = await _make_folder(pool, owner, owner)
    page = await _make_page(pool, owner, owner, folder_id=folder)
    file_id = await _make_file(pool, owner, owner, folder_id=folder)
    await _set_public(pool, "folders", folder, "write")

    assert await permission_service.check_access("page", page, stranger, require="write")
    assert await permission_service.check_access("file", file_id, None, require="read")
    assert await permission_service.check_access("folder", folder, None, require="read")


@pytest.mark.asyncio
async def test_public_folder_read_does_not_grant_write_to_contents(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    folder = await _make_folder(pool, owner, owner)
    page = await _make_page(pool, owner, owner, folder_id=folder)
    await _set_public(pool, "folders", folder, "read")

    assert await permission_service.check_access("page", page, stranger, require="read")
    assert not await permission_service.check_access("page", page, stranger, require="write")


@pytest.mark.asyncio
async def test_no_public_link_stays_private(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    page = await _make_page(pool, owner, owner)  # public_permission defaults to 'none'
    assert not await permission_service.check_access("page", page, stranger)
    assert not await permission_service.check_access("page", page, None)


@pytest.mark.asyncio
async def test_public_link_visibility_and_predicate_agree(pool):
    owner = await _make_user(pool)
    stranger = await _make_user(pool)
    page = await _make_page(pool, owner, owner)
    assert await permission_service.get_visibility("page", page) == "private"

    await _set_public(pool, "pages", page, "comment")
    assert await permission_service.get_visibility("page", page) == "public"
    # check_access and the SQL predicate answer identically for every viewer/level.
    for viewer in (owner, stranger, None):
        for require in ("read", "comment", "write"):
            boolean = await permission_service.check_access("page", page, viewer, require=require)
            predicate = await _predicate_says(pool, "page", page, viewer, require)
            assert boolean == predicate


@pytest.mark.asyncio
async def test_general_access_endpoint_makes_page_anonymously_readable(client: AsyncClient, pool):
    """End-to-end: owner sets 'anyone with the link', then a logged-out client
    (no Authorization header) reads the page through the canonical route."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Schematic", "content": "public diagram"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    page_url = f"/api/v1/pages/{page_id}"

    # Restricted by default: an anonymous read (no auth header) is a 404.
    assert (await client.get(page_url)).status_code == 404

    grant = await client.patch(
        "/api/v1/share/general-access",
        json={"object_type": "page", "object_id": page_id, "public_permission": "read"},
        headers=_auth(owner_key),
    )
    assert grant.status_code == 200
    assert grant.json()["public_permission"] == "read"

    # Now anyone with the link — logged out — can read it.
    anon = await client.get(page_url)
    assert anon.status_code == 200
    assert anon.json()["name"] == "Schematic"

    # The share list reports the current general-access level to the owner UI.
    shares = await client.get(
        "/api/v1/share",
        params={"object_type": "page", "object_id": page_id},
        headers=_auth(owner_key),
    )
    assert shares.json()["general_access"] == "read"


@pytest.mark.asyncio
async def test_general_access_owner_only(client: AsyncClient, pool):
    """Only the scope owner may change publicity; a stranger gets a 404 (the
    same not-found guard the share endpoints use)."""
    owner_key, _ = await _register(client)
    page_id = (
        await client.post(
            "/api/v1/me/pages/new",
            json={"name": "Plan", "content": "roadmap"},
            headers=_auth(owner_key),
        )
    ).json()["id"]
    stranger_key, _ = await _register(client)

    denied = await client.patch(
        "/api/v1/share/general-access",
        json={"object_type": "page", "object_id": page_id, "public_permission": "write"},
        headers=_auth(stranger_key),
    )
    assert denied.status_code == 404
    # And the page is still private to the stranger.
    assert (
        await client.get(f"/api/v1/pages/{page_id}", headers=_auth(stranger_key))
    ).status_code == 404
