"""Scope as a place, not a mode: reads span every scope the caller owns.

Why this matters:
- A read must not depend on ambient state. Before this, the same GET returned
  different content depending on a header the user set days earlier on a
  different machine, which is how sessions "disappeared" after switching.
- Spanning must not widen access by one row. The owner set comes from the same
  derived-membership predicate as everything else, so an unverified on-domain
  signup — the case that must never see a customer's KB — gains nothing.
- Writes stay single-scope on purpose: a new object has to land somewhere, and
  that destination is the one thing a caller still chooses.
"""

import uuid

import pytest
from httpx import AsyncClient

from backend.services import permission_service

from .conftest import unique_name
from .test_permissions import _auth, _register_with_email
from .test_workspaces import (
    ADMIN,
    _create_workspace,
    _domain,
    _verify_email,
    _workspace_page,
)


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    """Workspaces are created through the admin API, same as test_workspaces."""
    monkeypatch.setattr("backend.routers.admin.settings.ADMIN_PASSWORD", ADMIN["X-Admin-Token"])


async def _member_of_new_workspace(client: AsyncClient, pool) -> tuple[str, dict, dict]:
    """A verified on-domain user plus the workspace they derive membership in."""
    domain = _domain()
    key, body = await _register_with_email(client, f"{unique_name('m')}@{domain}")
    await _verify_email(pool, uuid.UUID(body["id"]))
    workspace = await _create_workspace(client, domain)
    return key, body, workspace


# --- The owner set itself ---


@pytest.mark.asyncio
async def test_read_scopes_are_just_yourself_without_a_workspace(client: AsyncClient):
    key, body = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    assert key
    scopes = await permission_service.read_scope_ids(uuid.UUID(body["id"]))
    assert scopes == [uuid.UUID(body["id"])]


@pytest.mark.asyncio
async def test_read_scopes_put_yourself_first_then_workspaces(client: AsyncClient, pool):
    _, body, workspace = await _member_of_new_workspace(client, pool)
    scopes = await permission_service.read_scope_ids(uuid.UUID(body["id"]))
    assert scopes == [uuid.UUID(body["id"]), uuid.UUID(workspace["scope_user_id"])]


@pytest.mark.asyncio
async def test_unverified_on_domain_signup_gets_no_workspace_scope(client: AsyncClient, pool):
    """The trust anchor. An unverified `fake@customer.com` must not read the
    customer's KB just because reads now span — membership is still derived from
    a *verified* email, and spanning reuses that one predicate.
    """
    domain = _domain()
    _, body = await _register_with_email(client, f"{unique_name('imposter')}@{domain}")
    workspace = await _create_workspace(client, domain)

    scopes = await permission_service.read_scope_ids(uuid.UUID(body["id"]))
    assert scopes == [uuid.UUID(body["id"])]
    assert uuid.UUID(workspace["scope_user_id"]) not in scopes


@pytest.mark.asyncio
async def test_read_scopes_exclude_workspaces_you_do_not_belong_to(client: AsyncClient, pool):
    _, outsider = await _register_with_email(client, f"{unique_name('out')}@elsewhere.io")
    _, _, workspace = await _member_of_new_workspace(client, pool)

    scopes = await permission_service.read_scope_ids(uuid.UUID(outsider["id"]))
    assert scopes == [uuid.UUID(outsider["id"])]
    assert uuid.UUID(workspace["scope_user_id"]) not in scopes


# --- Reads span without being told to ---


@pytest.mark.asyncio
async def test_trash_spans_scopes_and_says_which_place_each_row_came_from(
    client: AsyncClient, pool
):
    """Deleting something from the workspace and then hunting for it in a scope
    switcher is the confusion this model removes: one trash, rows labelled."""
    key, body, workspace = await _member_of_new_workspace(client, pool)
    org_page = await _workspace_page(pool, workspace["scope_user_id"], name="org-page")
    await pool.execute("UPDATE pages SET deleted_at = now() WHERE id = $1", org_page)

    mine = await client.post("/api/v1/me/pages/new", json={"name": "my-page"}, headers=_auth(key))
    assert mine.status_code in (200, 201), mine.text
    await client.delete(f"/api/v1/me/pages/{mine.json()['id']}", headers=_auth(key))

    resp = await client.get("/api/v1/me/trash", headers=_auth(key))
    assert resp.status_code == 200, resp.text
    pages = resp.json()["pages"]
    by_name = {page["name"]: page for page in pages}
    assert {"org-page", "my-page"} <= set(by_name)
    assert by_name["org-page"]["owner_user_id"] == workspace["scope_user_id"]
    assert by_name["my-page"]["owner_user_id"] == body["id"]


@pytest.mark.asyncio
async def test_trash_still_hides_other_scopes(client: AsyncClient, pool):
    """Spanning is "every scope you own", not "every scope"."""
    _, _, workspace = await _member_of_new_workspace(client, pool)
    org_page = await _workspace_page(pool, workspace["scope_user_id"], name="secret-org-page")
    await pool.execute("UPDATE pages SET deleted_at = now() WHERE id = $1", org_page)

    outsider_key, _ = await _register_with_email(client, f"{unique_name('out')}@elsewhere.io")
    resp = await client.get("/api/v1/me/trash", headers=_auth(outsider_key))
    assert resp.status_code == 200
    assert "secret-org-page" not in [page["name"] for page in resp.json()["pages"]]


@pytest.mark.asyncio
async def test_session_detail_resolves_the_scope_instead_of_being_told_it(
    client: AsyncClient, pool
):
    """A session streamed into the workspace is addressable by id alone. Under
    the old model this 404'd unless the caller re-sent the header that was set
    when the session was uploaded."""
    key, _, workspace = await _member_of_new_workspace(client, pool)
    session_id = str(uuid.uuid4())
    scoped = {**_auth(key), "X-Stash-Scope": workspace["scope_user_id"]}

    pushed = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "claude",
            "event_type": "user_message",
            "content": "work session in the org scope",
            "session_id": session_id,
        },
        headers=scoped,
    )
    assert pushed.status_code == 201, pushed.text

    resp = await client.get(f"/api/v1/me/sessions/{session_id}", headers=_auth(key))
    assert resp.status_code == 200, resp.text
    assert resp.json()["owner_user_id"] == workspace["scope_user_id"]


@pytest.mark.asyncio
async def test_session_detail_denies_scopes_you_do_not_own(client: AsyncClient, pool):
    key, _, workspace = await _member_of_new_workspace(client, pool)
    session_id = str(uuid.uuid4())
    await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "claude",
            "event_type": "user_message",
            "content": "org-only",
            "session_id": session_id,
        },
        headers={**_auth(key), "X-Stash-Scope": workspace["scope_user_id"]},
    )

    outsider_key, _ = await _register_with_email(client, f"{unique_name('out')}@elsewhere.io")
    resp = await client.get(f"/api/v1/me/sessions/{session_id}", headers=_auth(outsider_key))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_session_list_spans_scopes_with_no_header(client: AsyncClient, pool):
    key, body, workspace = await _member_of_new_workspace(client, pool)
    personal_session, org_session = str(uuid.uuid4()), str(uuid.uuid4())

    for session_id, headers in (
        (personal_session, _auth(key)),
        (org_session, {**_auth(key), "X-Stash-Scope": workspace["scope_user_id"]}),
    ):
        resp = await client.post(
            "/api/v1/me/sessions/events",
            json={
                "agent_name": "claude",
                "event_type": "user_message",
                "content": f"prompt for {session_id}",
                "session_id": session_id,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    resp = await client.get("/api/v1/me/sessions", headers=_auth(key))
    assert resp.status_code == 200, resp.text
    owners = {row["session_id"]: row["owner_user_id"] for row in resp.json()["sessions"]}
    assert owners.get(personal_session) == body["id"]
    assert owners.get(org_session) == workspace["scope_user_id"]


@pytest.mark.asyncio
async def test_session_list_header_no_longer_narrows_the_window(client: AsyncClient, pool):
    """The header is a write destination now. Sending it must not silently
    change what a read returns — that ambient narrowing is the bug."""
    key, _, workspace = await _member_of_new_workspace(client, pool)
    personal_session = str(uuid.uuid4())
    await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "claude",
            "event_type": "user_message",
            "content": "personal work",
            "session_id": personal_session,
        },
        headers=_auth(key),
    )

    scoped = await client.get(
        "/api/v1/me/sessions",
        headers={**_auth(key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert scoped.status_code == 200, scoped.text
    assert personal_session in [row["session_id"] for row in scoped.json()["sessions"]]


@pytest.mark.asyncio
async def test_owner_filter_still_narrows_when_asked_explicitly(client: AsyncClient, pool):
    """Narrowing is fine as a query the caller writes down; it just stops being
    ambient state."""
    key, body, workspace = await _member_of_new_workspace(client, pool)
    org_session = str(uuid.uuid4())
    await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "claude",
            "event_type": "user_message",
            "content": "org work",
            "session_id": org_session,
        },
        headers={**_auth(key), "X-Stash-Scope": workspace["scope_user_id"]},
    )

    resp = await client.get(
        "/api/v1/me/sessions",
        params={"owner_user_id": body["id"]},
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert org_session not in [row["session_id"] for row in resp.json()["sessions"]]
