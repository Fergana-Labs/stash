"""Tests for the POST /me/sessions/soft-delete bulk soft-delete endpoint (STAS-098).

Contract under test: a valid body always returns 200; each unique requested
session_id lands in at most one of the deleted / already_deleted / not_found
buckets, in request order. A row the caller lacks write access to is reported
not_found — the endpoint never confirms that an unreadable session exists.
"""

import uuid

import pytest
from httpx import AsyncClient

from .conftest import unique_name

ADMIN = {"X-Admin-Token": "test-admin-secret-token-at-least-32-chars-long"}


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    monkeypatch.setattr("backend.routers.admin.settings.ADMIN_PASSWORD", ADMIN["X-Admin-Token"])


async def _register(client: AsyncClient) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
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


def _headers(api_key: str, scope_user_id: str | None = None) -> dict:
    headers = _auth(api_key)
    if scope_user_id is not None:
        headers["X-Stash-Scope"] = scope_user_id
    return headers


async def _upsert_session(client: AsyncClient, api_key: str, session_id: str, scope_user_id: str | None = None):
    resp = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": session_id, "agent_name": "claude"},
        headers=_headers(api_key, scope_user_id),
    )
    assert resp.status_code == 201
    return resp.json()


async def _row(pool, owner_user_id, session_id):
    return await pool.fetchrow(
        "SELECT id, deleted_at, deleted_by FROM sessions "
        "WHERE owner_user_id = $1 AND session_id = $2",
        uuid.UUID(owner_user_id),
        session_id,
    )


async def _audit_count(pool, target_id) -> int:
    return await pool.fetchval(
        "SELECT count(*) FROM security_audit_events "
        "WHERE action = 'content.session_deleted' AND target_id = $1",
        str(target_id),
    )


async def _create_workspace(client: AsyncClient, domain: str, name: str = "Acme") -> dict:
    resp = await client.post(
        "/api/v1/admin/workspaces", json={"name": name, "domain": domain}, headers=ADMIN
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _verify_email(pool, user_id) -> None:
    await pool.execute("UPDATE users SET email_verified = true WHERE id = $1", user_id)


# --- Happy path: live rows, request order, audit trail ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_deletes_live_rows_in_request_order(client: AsyncClient, pool):
    api_key, user = await _register(client)
    owner = user["id"]
    for session_id in ("sess-a", "sess-b", "sess-c"):
        await _upsert_session(client, api_key, session_id)

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-c", "sess-a", "sess-b"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "deleted": ["sess-c", "sess-a", "sess-b"],
        "already_deleted": [],
        "not_found": [],
    }

    for session_id in ("sess-a", "sess-b", "sess-c"):
        row = await _row(pool, owner, session_id)
        assert row["deleted_at"] is not None
        assert str(row["deleted_by"]) == str(uuid.UUID(owner))
        assert await _audit_count(pool, row["id"]) == 1


# --- Outcome buckets: mixed states in one request, request order ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_mixed_outcomes_in_request_order(client: AsyncClient, pool):
    api_key, user = await _register(client)
    owner = user["id"]
    for session_id in ("sess-a", "sess-b", "sess-c"):
        await _upsert_session(client, api_key, session_id)

    # Pre-delete sess-c through the per-row route so the batch sees a trashed row.
    row_c = await _row(pool, owner, "sess-c")
    deleted = await client.delete(
        f"/api/v1/me/sessions/{row_c['id']}", headers=_auth(api_key)
    )
    assert deleted.status_code == 204

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-b", "sess-ghost", "sess-a", "sess-c"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "deleted": ["sess-b", "sess-a"],
        "already_deleted": ["sess-c"],
        "not_found": ["sess-ghost"],
    }


# --- Dedupe: duplicates collapse to one outcome, one row, one audit ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_dedupes_preserving_first_occurrence(client: AsyncClient, pool):
    api_key, user = await _register(client)
    owner = user["id"]
    await _upsert_session(client, api_key, "sess-d")

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-d", "sess-d", "sess-d"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": ["sess-d"], "already_deleted": [], "not_found": []}

    row = await _row(pool, owner, "sess-d")
    assert row["deleted_at"] is not None
    assert await _audit_count(pool, row["id"]) == 1


# --- Idempotency: a repeated batch reports already_deleted, never errors ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_is_idempotent_on_repeat(client: AsyncClient, pool):
    api_key, user = await _register(client)
    owner = user["id"]
    await _upsert_session(client, api_key, "sess-e")

    first = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-e"]},
        headers=_auth(api_key),
    )
    assert first.status_code == 200
    assert first.json()["deleted"] == ["sess-e"]

    second = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-e"]},
        headers=_auth(api_key),
    )
    assert second.status_code == 200
    assert second.json() == {"deleted": [], "already_deleted": ["sess-e"], "not_found": []}

    row = await _row(pool, owner, "sess-e")
    assert await _audit_count(pool, row["id"]) == 1


# --- Validation: 422 for malformed bodies, no partial application ---


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(None, id="missing-body"),
        pytest.param({"session_ids": []}, id="empty-list"),
        pytest.param({"session_ids": ["real-1"] + [f"ghost-{i:03d}" for i in range(100)]}, id="over-cap"),
        pytest.param({"session_ids": ["ok-1", 42]}, id="non-string-item"),
        pytest.param({"session_ids": [""]}, id="empty-string-item"),
        pytest.param({"session_ids": ["x" * 129]}, id="overlong-item"),
    ],
)
@pytest.mark.asyncio
async def test_bulk_soft_delete_rejects_invalid_bodies(client: AsyncClient, pool, body):
    api_key, user = await _register(client)
    if body is not None and "real-1" in body.get("session_ids", []):
        await _upsert_session(client, api_key, "real-1")

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json=body,
        headers=_auth(api_key),
    )
    assert resp.status_code == 422

    if body is not None and "real-1" in body.get("session_ids", []):
        row = await _row(pool, user["id"], "real-1")
        assert row is not None
        assert row["deleted_at"] is None


@pytest.mark.asyncio
async def test_bulk_soft_delete_accepts_exactly_100_items(client: AsyncClient, pool):
    api_key, _user = await _register(client)
    await _upsert_session(client, api_key, "live-1")

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["live-1"] + [f"ghost-{i:03d}" for i in range(99)]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == ["live-1"]
    assert len(body["not_found"]) == 99
    assert body["already_deleted"] == []


# --- No existence oracle: other-owner rows land in not_found, untouched ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_never_confirms_other_owner_session(client: AsyncClient, pool):
    owner_key, owner_user = await _register(client)
    stranger_key, stranger_user = await _register(client)
    await _upsert_session(client, stranger_key, "sess-cross")

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-cross"]},
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": [], "already_deleted": [], "not_found": ["sess-cross"]}

    row = await _row(pool, stranger_user["id"], "sess-cross")
    assert row["deleted_at"] is None
    assert await _audit_count(pool, row["id"]) == 0


# --- No write permission: reported not_found, row untouched, no audit ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_without_write_permission_reports_not_found(
    client: AsyncClient, pool, monkeypatch
):
    api_key, user = await _register(client)
    owner = user["id"]
    await _upsert_session(client, api_key, "sess-gated")
    row = await _row(pool, owner, "sess-gated")

    from backend.services import permission_service

    original = permission_service.check_access

    async def deny_session_write(object_type, object_id, user_id, owner_user_id=None, require="read"):
        if object_type == "session" and object_id == row["id"] and require == "write":
            return False
        return await original(
            object_type, object_id, user_id, owner_user_id=owner_user_id, require=require
        )

    monkeypatch.setattr(permission_service, "check_access", deny_session_write)

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-gated"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": [], "already_deleted": [], "not_found": ["sess-gated"]}

    after = await _row(pool, owner, "sess-gated")
    assert after["deleted_at"] is None
    assert await _audit_count(pool, row["id"]) == 0


# --- Auth: same gate as the sibling /me/sessions routes ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_requires_auth(client: AsyncClient):
    missing = await client.post(
        "/api/v1/me/sessions/soft-delete", json={"session_ids": ["sess-a"]}
    )
    assert missing.status_code == 401

    invalid = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-a"]},
        headers=_auth("not-a-real-key"),
    )
    assert invalid.status_code == 401


# --- Scope: workspace header re-roots the batch; personal view stays personal ---


@pytest.mark.asyncio
async def test_bulk_soft_delete_workspace_scope(client: AsyncClient, pool):
    domain = f"{unique_name('corp')}.com".lower()
    member_key, member = await _register_with_email(client, f"m@{domain}")
    await _verify_email(pool, uuid.UUID(member["id"]))
    ws = await _create_workspace(client, domain)
    scope = ws["scope_user_id"]

    await _upsert_session(client, member_key, "sess-org", scope_user_id=scope)
    org_row = await _row(pool, scope, "sess-org")
    assert org_row is not None

    resp = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-org"]},
        headers=_headers(member_key, scope),
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": ["sess-org"], "already_deleted": [], "not_found": []}
    assert (await _row(pool, scope, "sess-org"))["deleted_at"] is not None

    # The same id in the member's personal scope is a different row namespace.
    personal = await client.post(
        "/api/v1/me/sessions/soft-delete",
        json={"session_ids": ["sess-org"]},
        headers=_auth(member_key),
    )
    assert personal.status_code == 200
    assert personal.json() == {"deleted": [], "already_deleted": [], "not_found": ["sess-org"]}
