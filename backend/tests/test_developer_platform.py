"""Developer platform + External Multiplayer.

What matters here:
- Activation is self-serve and idempotent: a solo developer gets a one-man,
  invite-only (NULL-domain) workspace with the wiki and notepads folders; the
  creator is an explicit member, since no domain rule will ever cover them.
- The tenant contract: `tenant_id` on an events upload names the developer's own
  customer id. First sight creates the tenant and its notepad folder; the
  session row is stamped set-once, so a tenant session can never migrate to
  another tenant later.
- Tenant ids only work on developer workspace scopes — a personal upload
  carrying tenant_id fails loud, it never silently drops the tenant.
- The tenant-scoped VFS shows one tenant's world and nothing else's: the shared
  wiki at /memory, that tenant's notepad and files under /files, that tenant's
  transcripts under /sessions. Another tenant's material must be invisible —
  that is the entire product promise to the developer's customers.
"""

import uuid

import pytest
from httpx import AsyncClient

from .conftest import unique_name
from .test_permissions import _auth, _register_with_email


async def _developer(client: AsyncClient) -> tuple[str, dict, dict]:
    """A registered user with an activated developer workspace.
    Returns (user_api_key, user_body, workspace)."""
    email = f"{unique_name('dev')}@example.com"
    api_key, body = await _register_with_email(client, email)
    resp = await client.post("/api/v1/me/developer/activate", json={}, headers=_auth(api_key))
    assert resp.status_code == 200, resp.text
    return api_key, body, resp.json()


async def _mint_workspace_key(client: AsyncClient, api_key: str, workspace: dict) -> str:
    resp = await client.post(
        "/api/v1/me/developer/keys",
        json={"name": "prod", "access": "read"},
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["api_key"]


def _event(session_id: str, tenant_id: str | None = None, tenant_name: str | None = None) -> dict:
    event = {
        "agent_name": "heavi-chat",
        "event_type": "user_message",
        "content": f"hello from {session_id}",
        "session_id": session_id,
    }
    if tenant_id is not None:
        event["tenant_id"] = tenant_id
    if tenant_name is not None:
        event["tenant_name"] = tenant_name
    return event


async def _push(client: AsyncClient, key: str, events: list[dict]) -> None:
    resp = await client.post(
        "/api/v1/me/sessions/events/batch", json={"events": events}, headers=_auth(key)
    )
    assert resp.status_code == 201, resp.text


# --- Activation ---


@pytest.mark.asyncio
async def test_activate_creates_one_man_workspace(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)

    assert workspace["domain"] is None
    assert workspace["external_wiki_folder_id"] is not None
    assert workspace["tenant_notepads_folder_id"] is not None

    # The creator is an explicit member: the workspace scope works for them.
    resp = await client.get(
        "/api/v1/me/overview",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200

    # And it is invite-only: a stranger is not a member.
    stranger_key, _ = await _register_with_email(client, f"{unique_name('other')}@example.com")
    resp = await client.get(
        "/api/v1/me/overview",
        headers={**_auth(stranger_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_activate_is_idempotent(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    resp = await client.post(
        "/api/v1/me/developer/activate",
        json={"workspace_id": workspace["id"]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    again = resp.json()
    assert again["external_wiki_folder_id"] == workspace["external_wiki_folder_id"]


# --- The tenant write contract ---


@pytest.mark.asyncio
async def test_tenant_upload_creates_tenant_and_stamps_session(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(
        client,
        machine_key,
        [_event("sess-riverside-1", tenant_id="org_riverside", tenant_name="Riverside Truck")],
    )

    tenant = await pool.fetchrow(
        "SELECT * FROM tenants WHERE workspace_id = $1 AND external_id = 'org_riverside'",
        uuid.UUID(workspace["id"]),
    )
    assert tenant is not None
    assert tenant["name"] == "Riverside Truck"
    assert tenant["share_wiki"] is True
    assert tenant["notepad_folder_id"] is not None

    session = await pool.fetchrow(
        "SELECT tenant_id FROM sessions WHERE owner_user_id = $1 AND session_id = 'sess-riverside-1'",
        uuid.UUID(workspace["scope_user_id"]),
    )
    assert session["tenant_id"] == tenant["id"]


@pytest.mark.asyncio
async def test_one_tenant_appends_to_its_session_across_batches(client: AsyncClient, pool):
    """The ordinary case the collision guard must not break: a customer's agent
    pushes turn after turn under the same session id, and they accumulate in one
    session belonging to that customer."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    for _ in range(3):
        await _push(
            client, machine_key, [_event("sess-sticky", tenant_id="org_a", tenant_name="A")]
        )

    rows = await pool.fetch(
        "SELECT o.external_id FROM sessions s JOIN tenants o ON o.id = s.tenant_id "
        "WHERE s.owner_user_id = $1 AND s.session_id = 'sess-sticky'",
        uuid.UUID(workspace["scope_user_id"]),
    )
    assert [r["external_id"] for r in rows] == ["org_a"]
    events = await pool.fetchval(
        "SELECT count(*) FROM history_events WHERE owner_user_id = $1 AND session_id = 'sess-sticky'",
        uuid.UUID(workspace["scope_user_id"]),
    )
    assert events == 3


@pytest.mark.asyncio
async def test_tenant_upload_on_personal_scope_fails_loud(client: AsyncClient):
    api_key, _ = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("sess-1", tenant_id="org_x")]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400
    assert "workspace" in resp.json()["detail"]


# --- The tenant read contract (VFS) ---


@pytest.mark.asyncio
async def test_tenant_vfs_isolates_orgs(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(
        client,
        machine_key,
        [
            _event("sess-acme-1", tenant_id="org_acme", tenant_name="Acme"),
            _event("sess-beta-1", tenant_id="org_beta", tenant_name="Beta"),
            _event("sess-internal"),
        ],
    )

    # Seed a wiki page (shared) and a page in each tenant's notepad.
    tenants = {
        r["external_id"]: r
        for r in await pool.fetch(
            "SELECT external_id, notepad_folder_id FROM tenants WHERE workspace_id = $1",
            uuid.UUID(workspace["id"]),
        )
    }
    scope_id = uuid.UUID(workspace["scope_user_id"])
    for name, folder_id in [
        ("Fault codes", uuid.UUID(workspace["external_wiki_folder_id"])),
        ("Acme notes", tenants["org_acme"]["notepad_folder_id"]),
        ("Beta notes", tenants["org_beta"]["notepad_folder_id"]),
    ]:
        await pool.execute(
            "INSERT INTO pages (owner_user_id, name, content_markdown, folder_id, created_by) "
            "VALUES ($1, $2, 'body', $3, $1)",
            scope_id,
            name,
            folder_id,
        )

    resp = await client.post(
        "/api/v1/me/vfs",
        json={"script": "find / -type f", "tenant_id": "org_acme"},
        headers=_auth(machine_key),
    )
    assert resp.status_code == 200, resp.text
    listing = resp.json()["stdout"]

    # Acme's world: the shared wiki, its own notepad, its own session.
    assert "Fault codes" in listing
    assert "Acme notes" in listing
    assert "sess-acme-1" in listing or "hello from sess-acme-1" in listing

    # Nothing of Beta's or the developer's internal activity.
    assert "Beta notes" not in listing
    assert "sess-beta-1" not in listing
    assert "sess-internal" not in listing


@pytest.mark.asyncio
async def test_new_tenant_reads_the_shared_wiki_before_it_has_written(client: AsyncClient, pool):
    """A customer's agent reads context before it records anything, so its very
    first call names a tenant that has no row yet. That has to work, and it has to
    return the shared wiki: the accumulated cross-tenant knowledge is exactly what
    a brand-new customer benefits from on day one. Failing here would mean a
    customer can only read the wiki after contributing to it."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await pool.execute(
        "INSERT INTO pages (owner_user_id, name, content_markdown, folder_id, created_by) "
        "VALUES ($1, 'Fault codes', 'body', $2, $1)",
        uuid.UUID(workspace["scope_user_id"]),
        uuid.UUID(workspace["external_wiki_folder_id"]),
    )

    resp = await client.post(
        "/api/v1/me/vfs",
        json={"script": "find / -type f", "tenant_id": "org_never_seen"},
        headers=_auth(machine_key),
    )
    assert resp.status_code == 200, resp.text
    listing = resp.json()["stdout"]
    assert "Fault codes" in listing
    # It owns nothing yet — no notepad, no sessions of its own.
    assert "notepad" not in listing


@pytest.mark.asyncio
async def test_session_id_with_a_slash_is_refused(client: AsyncClient):
    """A slash makes the id unusable on the transcript endpoints, where it is a
    path parameter. The write would still succeed and the session would still
    list and grep — only `cat` on its transcript would 404, months later, for a
    subset of the data. Refuse it at the door, and say what to use instead."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("acme/conv-1", tenant_id="org_a", tenant_name="A")]},
        headers=_auth(machine_key),
    )
    assert resp.status_code == 422
    assert "acme:conv-1" in str(resp.json()["detail"])

    ok = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("acme:conv-1", tenant_id="org_a", tenant_name="A")]},
        headers=_auth(machine_key),
    )
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_two_orgs_cannot_share_a_session_id(client: AsyncClient, pool):
    """Session ids come from the developer's own app, so two of their customers
    picking the same one is ordinary. Sessions are unique on (owner, session_id)
    and the owner is the workspace, so appending regardless files one customer's
    turn inside another customer's transcript — where that customer's agent can
    read it. This is the isolation the whole feature promises."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(client, machine_key, [_event("conv-1", tenant_id="org_one", tenant_name="One")])

    collision = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("conv-1", tenant_id="org_two", tenant_name="Two")]},
        headers=_auth(machine_key),
    )
    assert collision.status_code == 400
    assert "conv-1" in collision.json()["detail"]

    # Refused before anything was stored: the first customer's session holds
    # only its own turn, and the second customer has no session at all.
    rows = await pool.fetch(
        "SELECT o.external_id FROM sessions s JOIN tenants o ON o.id = s.tenant_id "
        "WHERE s.session_id = 'conv-1'"
    )
    assert [r["external_id"] for r in rows] == ["org_one"]
    contents = [
        r["content"]
        for r in await pool.fetch(
            "SELECT content FROM history_events WHERE session_id = 'conv-1' ORDER BY created_at"
        )
    ]
    assert len(contents) == 1, contents


# --- The console API ---


@pytest.mark.asyncio
async def test_console_lists_orgs_with_counts(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s1", tenant_id="org_acme", tenant_name="Acme"),
            _event("s2", tenant_id="org_acme", tenant_name="Acme"),
        ],
    )

    resp = await client.get(
        "/api/v1/me/tenants",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    tenants = resp.json()["tenants"]
    assert len(tenants) == 1
    assert tenants[0]["external_id"] == "org_acme"
    assert tenants[0]["session_count"] == 2


@pytest.mark.asyncio
async def test_console_wiki_opt_out(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, machine_key, [_event("s1", tenant_id="org_acme", tenant_name="Acme")])

    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}
    tenant = (await client.get("/api/v1/me/tenants", headers=scope)).json()["tenants"][0]

    resp = await client.patch(
        f"/api/v1/me/tenants/{tenant['id']}", json={"share_wiki": False}, headers=scope
    )
    assert resp.status_code == 200
    assert resp.json()["share_wiki"] is False

    # A member of a different workspace can't touch it.
    other_key, _, other_ws = await _developer(client)
    resp = await client.patch(
        f"/api/v1/me/tenants/{tenant['id']}",
        json={"share_wiki": True},
        headers={**_auth(other_key), "X-Stash-Scope": other_ws["scope_user_id"]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_console_sessions_labelled_by_tenant(client: AsyncClient):
    """The console's sessions list is the cross-tenant view: every session the
    workspace recorded, each carrying its tenant label — and tenant-less rows
    (the workspace's own agents) still listed rather than hidden."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s-acme", tenant_id="org_acme", tenant_name="Acme"),
            _event("s-beta", tenant_id="org_beta", tenant_name="Beta"),
            _event("s-internal"),
        ],
    )

    resp = await client.get(
        "/api/v1/me/developer/sessions",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    rows = {r["session_id"]: r for r in resp.json()["sessions"]}
    assert rows["s-acme"]["tenant_name"] == "Acme"
    assert rows["s-beta"]["tenant_external_id"] == "org_beta"
    assert rows["s-internal"]["tenant_id"] is None
    assert rows["s-acme"]["event_count"] == 1


@pytest.mark.asyncio
async def test_console_files_split_by_wiki_and_tenant(client: AsyncClient, pool):
    """The files view answers 'whose is this?' by construction: shared wiki
    material in one pile, each tenant's own pages in theirs — never mixed."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s-acme", tenant_id="org_acme", tenant_name="Acme"),
            _event("s-beta", tenant_id="org_beta", tenant_name="Beta"),
        ],
    )
    tenants = {
        r["external_id"]: r
        for r in await pool.fetch(
            "SELECT external_id, notepad_folder_id FROM tenants WHERE workspace_id = $1",
            uuid.UUID(workspace["id"]),
        )
    }
    scope_id = uuid.UUID(workspace["scope_user_id"])
    for name, folder_id in [
        ("Fault codes", uuid.UUID(workspace["external_wiki_folder_id"])),
        ("Acme notes", tenants["org_acme"]["notepad_folder_id"]),
    ]:
        await pool.execute(
            "INSERT INTO pages (owner_user_id, name, content_markdown, folder_id, created_by) "
            "VALUES ($1, $2, 'body', $3, $1)",
            scope_id,
            name,
            folder_id,
        )

    resp = await client.get(
        "/api/v1/me/developer/files",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [p["name"] for p in body["wiki_pages"]] == ["Fault codes"]
    by_tenant = {t["external_id"]: t for t in body["tenants"]}
    assert [p["name"] for p in by_tenant["org_acme"]["notepad_pages"]] == ["Acme notes"]
    assert by_tenant["org_beta"]["notepad_pages"] == []


@pytest.mark.asyncio
async def test_curator_instructions_roundtrip(client: AsyncClient):
    """The instructions are the developer's one hook into the curator's prompt:
    a save must come back on the next read, and an empty save must clear them
    rather than storing an empty persona."""
    api_key, _, workspace = await _developer(client)
    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}

    resp = await client.get("/api/v1/me/developer/curator", headers=scope)
    assert resp.status_code == 200, resp.text
    assert resp.json()["instructions"] is None
    assert "full history" in resp.json()["backfill_prompt"]

    resp = await client.patch(
        "/api/v1/me/developer/curator",
        json={"instructions": "Never share pricing between tenants."},
        headers=scope,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["instructions"] == "Never share pricing between tenants."

    resp = await client.get("/api/v1/me/developer/curator", headers=scope)
    assert resp.json()["instructions"] == "Never share pricing between tenants."

    resp = await client.patch(
        "/api/v1/me/developer/curator", json={"instructions": ""}, headers=scope
    )
    assert resp.status_code == 200
    assert resp.json()["instructions"] is None


@pytest.mark.asyncio
async def test_backfill_clears_watermark_and_dispatches(client: AsyncClient, monkeypatch):
    """Backfill means 'read everything again': the watermark must clear so the
    dispatched run renders the full-history prompt."""
    from backend.tasks import agent_schedules

    dispatched: list[str] = []
    monkeypatch.setattr(
        agent_schedules.run_curator_now, "delay", lambda agent_id: dispatched.append(agent_id)
    )

    api_key, _, workspace = await _developer(client)
    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}

    # Creating the curator seeds a bounded-backfill watermark.
    resp = await client.get("/api/v1/me/developer/curator", headers=scope)
    assert resp.json()["curator"]["curated_through"] is not None

    resp = await client.post("/api/v1/me/developer/curator/backfill", headers=scope)
    assert resp.status_code == 202, resp.text
    assert len(dispatched) == 1

    resp = await client.get("/api/v1/me/developer/curator", headers=scope)
    assert resp.json()["curator"]["curated_through"] is None


async def test_key_list_and_revoke(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}
    minted = await _mint_workspace_key(client, api_key, workspace)

    listed = await client.get("/api/v1/me/developer/keys", headers=scope)
    assert listed.status_code == 200, listed.text
    keys = listed.json()["keys"]
    assert [k["name"] for k in keys] == ["prod"]
    assert keys[0]["access"] == "read"
    # Key material is shown once, at mint — never by the list. What the list
    # carries is the recognition fragment stamped at mint time.
    assert "api_key" not in keys[0] and "key_hash" not in keys[0]
    assert keys[0]["key_prefix"] == minted[:8]
    assert keys[0]["key_suffix"] == minted[-4:]

    # The minted key works before revocation…
    ok = await client.post("/api/v1/me/vfs", json={"script": "ls /"}, headers=_auth(minted))
    assert ok.status_code == 200, ok.text

    revoked = await client.delete(f"/api/v1/me/developer/keys/{keys[0]['id']}", headers=scope)
    assert revoked.status_code == 200, revoked.text

    # …is refused after, and is gone from the list.
    denied = await client.post("/api/v1/me/vfs", json={"script": "ls /"}, headers=_auth(minted))
    assert denied.status_code == 401
    assert (await client.get("/api/v1/me/developer/keys", headers=scope)).json()["keys"] == []

    # Revoking an already-revoked key is a 404, not a silent success.
    again = await client.delete(f"/api/v1/me/developer/keys/{keys[0]['id']}", headers=scope)
    assert again.status_code == 404
