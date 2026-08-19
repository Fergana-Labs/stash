"""Developer platform + External Multiplayer.

What matters here:
- Activation is self-serve and idempotent: a solo developer gets a one-man,
  invite-only (NULL-domain) workspace with the wiki and notepads folders; the
  creator is an explicit member, since no domain rule will ever cover them.
- The org contract: `org_id` on an events upload names the developer's own
  customer id. First sight creates the org and its notepad folder; the
  session row is stamped set-once, so an org session can never migrate to
  another org later.
- Org ids only work on developer workspace scopes — a personal upload
  carrying org_id fails loud, it never silently drops the org.
- The org-scoped VFS shows one org's world and nothing else's: the shared
  wiki at /memory, that org's notepad and files under /files, that org's
  transcripts under /sessions. Another org's material must be invisible —
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


def _event(session_id: str, org_id: str | None = None, org_name: str | None = None) -> dict:
    event = {
        "agent_name": "heavi-chat",
        "event_type": "user_message",
        "content": f"hello from {session_id}",
        "session_id": session_id,
    }
    if org_id is not None:
        event["org_id"] = org_id
    if org_name is not None:
        event["org_name"] = org_name
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
    assert workspace["org_notepads_folder_id"] is not None

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


# --- The org write contract ---


@pytest.mark.asyncio
async def test_org_upload_creates_org_and_stamps_session(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(
        client,
        machine_key,
        [_event("sess-riverside-1", org_id="org_riverside", org_name="Riverside Truck")],
    )

    org = await pool.fetchrow(
        "SELECT * FROM orgs WHERE workspace_id = $1 AND external_id = 'org_riverside'",
        uuid.UUID(workspace["id"]),
    )
    assert org is not None
    assert org["name"] == "Riverside Truck"
    assert org["share_wiki"] is True
    assert org["notepad_folder_id"] is not None

    session = await pool.fetchrow(
        "SELECT org_id FROM sessions WHERE owner_user_id = $1 AND session_id = 'sess-riverside-1'",
        uuid.UUID(workspace["scope_user_id"]),
    )
    assert session["org_id"] == org["id"]


@pytest.mark.asyncio
async def test_org_is_set_once_like_folders(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(client, machine_key, [_event("sess-sticky", org_id="org_a", org_name="A")])
    # A later event asserting a different org must not migrate the session.
    await _push(client, machine_key, [_event("sess-sticky", org_id="org_b", org_name="B")])

    row = await pool.fetchrow(
        "SELECT o.external_id FROM sessions s JOIN orgs o ON o.id = s.org_id "
        "WHERE s.owner_user_id = $1 AND s.session_id = 'sess-sticky'",
        uuid.UUID(workspace["scope_user_id"]),
    )
    assert row["external_id"] == "org_a"


@pytest.mark.asyncio
async def test_org_upload_on_personal_scope_fails_loud(client: AsyncClient):
    api_key, _ = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("sess-1", org_id="org_x")]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400
    assert "workspace" in resp.json()["detail"]


# --- The org read contract (VFS) ---


@pytest.mark.asyncio
async def test_org_vfs_isolates_orgs(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(
        client,
        machine_key,
        [
            _event("sess-acme-1", org_id="org_acme", org_name="Acme"),
            _event("sess-beta-1", org_id="org_beta", org_name="Beta"),
            _event("sess-internal"),
        ],
    )

    # Seed a wiki page (shared) and a page in each org's notepad.
    orgs = {
        r["external_id"]: r
        for r in await pool.fetch(
            "SELECT external_id, notepad_folder_id FROM orgs WHERE workspace_id = $1",
            uuid.UUID(workspace["id"]),
        )
    }
    scope_id = uuid.UUID(workspace["scope_user_id"])
    for name, folder_id in [
        ("Fault codes", uuid.UUID(workspace["external_wiki_folder_id"])),
        ("Acme notes", orgs["org_acme"]["notepad_folder_id"]),
        ("Beta notes", orgs["org_beta"]["notepad_folder_id"]),
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
        json={"script": "find / -type f", "org_id": "org_acme"},
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
async def test_org_vfs_unknown_org_fails_loud(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    resp = await client.post(
        "/api/v1/me/vfs",
        json={"script": "ls /", "org_id": "org_never_seen"},
        headers=_auth(machine_key),
    )
    assert resp.status_code == 400


# --- The console API ---


@pytest.mark.asyncio
async def test_console_lists_orgs_with_counts(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s1", org_id="org_acme", org_name="Acme"),
            _event("s2", org_id="org_acme", org_name="Acme"),
        ],
    )

    resp = await client.get(
        "/api/v1/me/orgs",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    orgs = resp.json()["orgs"]
    assert len(orgs) == 1
    assert orgs[0]["external_id"] == "org_acme"
    assert orgs[0]["session_count"] == 2


@pytest.mark.asyncio
async def test_console_wiki_opt_out(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, machine_key, [_event("s1", org_id="org_acme", org_name="Acme")])

    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}
    org = (await client.get("/api/v1/me/orgs", headers=scope)).json()["orgs"][0]

    resp = await client.patch(
        f"/api/v1/me/orgs/{org['id']}", json={"share_wiki": False}, headers=scope
    )
    assert resp.status_code == 200
    assert resp.json()["share_wiki"] is False

    # A member of a different workspace can't touch it.
    other_key, _, other_ws = await _developer(client)
    resp = await client.patch(
        f"/api/v1/me/orgs/{org['id']}",
        json={"share_wiki": True},
        headers={**_auth(other_key), "X-Stash-Scope": other_ws["scope_user_id"]},
    )
    assert resp.status_code == 403
