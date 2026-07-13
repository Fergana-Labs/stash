"""Workspaces: org-owned scopes with stored membership.

What matters here:
- Membership (not email text) grants access to the workspace KB, and email
  verification is the trust anchor for domain auto-enroll — an unverified
  `fake@customer.com` signup must never see the customer's knowledge base.
- The X-Stash-Scope header re-roots content routes for members only.
- Owner-only powers (sharing, key minting) never leak to members.
- A read-access workspace key can feed the KB (transcripts) but not destroy it.
"""

import uuid

import pytest
from httpx import AsyncClient

from backend.services import workspace_service

from .conftest import unique_name
from .test_permissions import _auth, _register_with_email

ADMIN = {"X-Admin-Token": "test-admin-secret-token-at-least-32-chars-long"}


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    monkeypatch.setattr("backend.routers.admin.settings.ADMIN_PASSWORD", ADMIN["X-Admin-Token"])


def _domain() -> str:
    return f"{unique_name('corp')}.com".lower()


async def _create_workspace(client: AsyncClient, domain: str, name: str = "Acme") -> dict:
    resp = await client.post(
        "/api/v1/admin/workspaces", json={"name": name, "domain": domain}, headers=ADMIN
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _verify_email(pool, user_id) -> None:
    await pool.execute("UPDATE users SET email_verified = true WHERE id = $1", user_id)


async def _workspace_page(pool, scope_user_id, name="org-page") -> uuid.UUID:
    row = await pool.fetchrow(
        "INSERT INTO pages (owner_user_id, name, content_markdown, created_by) "
        "VALUES ($1, $2, 'enterprise knowledge', $1) RETURNING id",
        uuid.UUID(scope_user_id),
        name,
    )
    return row["id"]


# --- Creation ---


@pytest.mark.asyncio
async def test_admin_creates_workspace_with_working_bootstrap_key(client: AsyncClient, pool):
    ws = await _create_workspace(client, _domain())

    scope_user = await pool.fetchrow(
        "SELECT plan, password_hash, auth0_sub, email FROM users WHERE id = $1",
        uuid.UUID(ws["scope_user_id"]),
    )
    # Enterprise entitlement, and login-less: the scope is reachable only
    # through minted keys.
    assert scope_user["plan"] == "enterprise"
    assert scope_user["password_hash"] is None
    assert scope_user["auth0_sub"] is None
    assert scope_user["email"] is None

    resp = await client.get("/api/v1/me/overview", headers=_auth(ws["bootstrap_api_key"]))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_domain_conflicts(client: AsyncClient):
    domain = _domain()
    await _create_workspace(client, domain)
    resp = await client.post(
        "/api/v1/admin/workspaces", json={"name": "Again", "domain": domain}, headers=ADMIN
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_domain_must_be_bare_and_lowercase(client: AsyncClient):
    for bad in ("Corp.Com", "user@corp.com", "corp", ""):
        resp = await client.post(
            "/api/v1/admin/workspaces", json={"name": "Bad", "domain": bad}, headers=ADMIN
        )
        assert resp.status_code == 400, bad


# --- Membership: verified-domain backfill, explicit adds, removal ---


@pytest.mark.asyncio
async def test_verified_domain_user_is_backfilled_and_reads_kb(client: AsyncClient, pool):
    domain = _domain()
    key, body = await _register_with_email(client, f"alice@{domain}")
    await _verify_email(pool, uuid.UUID(body["id"]))

    ws = await _create_workspace(client, domain)
    page_id = await _workspace_page(pool, ws["scope_user_id"])

    resp = await client.get("/api/v1/me/workspaces", headers=_auth(key))
    assert [w["name"] for w in resp.json()["workspaces"]] == ["Acme"]

    # By-id access from anywhere (search results, links) uses the canonical
    # route, which resolves the real owner and applies the membership branch.
    resp = await client.get(f"/api/v1/pages/{page_id}", headers=_auth(key))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unverified_same_domain_email_gets_nothing(client: AsyncClient, pool):
    """The exfiltration path this feature must never open: sign up with an
    unverified email on the customer's domain, read their KB."""
    domain = _domain()
    key, _ = await _register_with_email(client, f"mallory@{domain}")

    ws = await _create_workspace(client, domain)
    page_id = await _workspace_page(pool, ws["scope_user_id"])

    resp = await client.get("/api/v1/me/workspaces", headers=_auth(key))
    assert resp.json()["workspaces"] == []
    resp = await client.get(f"/api/v1/pages/{page_id}", headers=_auth(key))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enroll_by_domain_on_login_joins_existing_workspace(client: AsyncClient, pool):
    """Auto-enroll also runs for users who sign up after the workspace exists
    (the Auth0 login path calls enroll_by_domain with verified emails)."""
    domain = _domain()
    ws = await _create_workspace(client, domain)

    key, body = await _register_with_email(client, f"late@{domain}")
    user_id = uuid.UUID(body["id"])
    await _verify_email(pool, user_id)
    await workspace_service.enroll_by_domain(user_id, f"late@{domain}")

    page_id = await _workspace_page(pool, ws["scope_user_id"])
    resp = await client.get(f"/api/v1/pages/{page_id}", headers=_auth(key))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_adds_and_removes_off_domain_member(client: AsyncClient, pool):
    ws = await _create_workspace(client, _domain())
    page_id = await _workspace_page(pool, ws["scope_user_id"])
    contractor_email = f"{unique_name('c')}@elsewhere.io"
    key, body = await _register_with_email(client, contractor_email)

    resp = await client.post(
        f"/api/v1/admin/workspaces/{ws['workspace_id']}/members",
        json={"email": contractor_email},
        headers=ADMIN,
    )
    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/pages/{page_id}", headers=_auth(key))).status_code == 200

    resp = await client.delete(
        f"/api/v1/admin/workspaces/{ws['workspace_id']}/members/{body['id']}",
        headers=ADMIN,
    )
    assert resp.status_code == 200
    # Removal revokes access immediately — membership is the single source of truth.
    assert (await client.get(f"/api/v1/pages/{page_id}", headers=_auth(key))).status_code == 404


# --- Member read+write ---


@pytest.mark.asyncio
async def test_member_can_edit_workspace_page(client: AsyncClient, pool):
    domain = _domain()
    key, body = await _register_with_email(client, f"editor@{domain}")
    await _verify_email(pool, uuid.UUID(body["id"]))
    ws = await _create_workspace(client, domain)
    page_id = await _workspace_page(pool, ws["scope_user_id"])

    resp = await client.patch(
        f"/api/v1/me/pages/{page_id}",
        json={"content_markdown": "member contribution"},
        headers={**_auth(key), "X-Stash-Scope": ws["scope_user_id"]},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_member_cannot_manage_workspace_shares(client: AsyncClient, pool):
    """Sharing is an owner power: a member must not be able to share (leak)
    the org KB to outsiders."""
    domain = _domain()
    key, body = await _register_with_email(client, f"editor@{domain}")
    await _verify_email(pool, uuid.UUID(body["id"]))
    ws = await _create_workspace(client, domain)
    page_id = await _workspace_page(pool, ws["scope_user_id"])

    resp = await client.post(
        "/api/v1/share",
        json={
            "object_type": "page",
            "object_id": str(page_id),
            "email": f"{unique_name('s')}@other.io",
            "permission": "read",
        },
        headers=_auth(key),
    )
    assert resp.status_code == 404


# --- The scope switcher header ---


@pytest.mark.asyncio
async def test_scope_header_reroots_overview_for_members_only(client: AsyncClient, pool):
    domain = _domain()
    member_key, member = await _register_with_email(client, f"m@{domain}")
    await _verify_email(pool, uuid.UUID(member["id"]))
    outsider_key, _ = await _register_with_email(client, f"{unique_name('o')}@other.io")
    ws = await _create_workspace(client, domain)
    await _workspace_page(pool, ws["scope_user_id"], name="org-only-page")

    scoped = {**_auth(member_key), "X-Stash-Scope": ws["scope_user_id"]}
    resp = await client.get("/api/v1/me/overview", headers=scoped)
    assert resp.status_code == 200
    assert "org-only-page" in [p["name"] for p in resp.json()["files"]["pages"]]

    # Personal view stays personal — the org page is not merged in.
    resp = await client.get("/api/v1/me/overview", headers=_auth(member_key))
    assert "org-only-page" not in [p["name"] for p in resp.json()["files"]["pages"]]

    resp = await client.get(
        "/api/v1/me/overview", headers={**_auth(outsider_key), "X-Stash-Scope": ws["scope_user_id"]}
    )
    assert resp.status_code == 403

    resp = await client.get(
        "/api/v1/me/overview", headers={**_auth(member_key), "X-Stash-Scope": "not-a-uuid"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_member_creates_page_owned_by_workspace(client: AsyncClient, pool):
    domain = _domain()
    key, body = await _register_with_email(client, f"m@{domain}")
    member_id = uuid.UUID(body["id"])
    await _verify_email(pool, member_id)
    ws = await _create_workspace(client, domain)

    scoped = {**_auth(key), "X-Stash-Scope": ws["scope_user_id"]}
    resp = await client.post("/api/v1/me/pages/new", json={"name": "from-member"}, headers=scoped)
    assert resp.status_code == 201, resp.text
    row = await pool.fetchrow(
        "SELECT owner_user_id, created_by FROM pages WHERE id = $1",
        uuid.UUID(resp.json()["id"]),
    )
    # Content belongs to the org; the action belongs to the human.
    assert row["owner_user_id"] == uuid.UUID(ws["scope_user_id"])
    assert row["created_by"] == member_id


# --- Workspace API keys ---


@pytest.mark.asyncio
async def test_read_key_feeds_but_cannot_destroy_the_kb(client: AsyncClient, pool):
    ws = await _create_workspace(client, _domain())
    resp = await client.post(
        f"/api/v1/admin/workspaces/{ws['workspace_id']}/keys",
        json={"name": "heavi prod", "access": "read"},
        headers=ADMIN,
    )
    assert resp.status_code == 200
    read_key = resp.json()["api_key"]

    page_id = await _workspace_page(pool, ws["scope_user_id"])
    assert (
        await client.get(f"/api/v1/me/pages/{page_id}", headers=_auth(read_key))
    ).status_code == 200

    resp = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("prod.jsonl", b'{"type": "user", "message": "hi"}\n')},
        data={"session_id": unique_name("sess"), "agent_name": "heavi-prod"},
        headers=_auth(read_key),
    )
    assert resp.status_code == 201, resp.text

    resp = await client.delete(f"/api/v1/me/pages/{page_id}", headers=_auth(read_key))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_workspace_key_endpoint_rejects_unknown_access(client: AsyncClient):
    ws = await _create_workspace(client, _domain())
    resp = await client.post(
        f"/api/v1/admin/workspaces/{ws['workspace_id']}/keys",
        json={"name": "bad", "access": "admin"},
        headers=ADMIN,
    )
    assert resp.status_code == 400
