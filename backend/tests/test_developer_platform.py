"""Developer platform + External Multiplayer.

What matters here:
- Activation is self-serve and idempotent: a solo developer gets a one-man,
  invite-only (NULL-domain) workspace with the wiki and notepads folders; the
  creator is an explicit member, since no domain rule will ever cover them.
- The user contract: `user_id` on an events upload names the developer's own
  id for their end user. First sight creates the user and their notepad folder;
  the session row is stamped set-once, so a user's session can never migrate to
  another user later.
- User ids only work on developer workspace scopes — a personal upload
  carrying user_id fails loud, it never silently drops the user.
- The user-scoped VFS shows one user's world and nothing else's: the shared
  wiki at /memory, that user's notepad and files under /files, that user's
  transcripts under /sessions. Another user's material must be invisible —
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


def _event(session_id: str, user_id: str | None = None, user_name: str | None = None) -> dict:
    event = {
        "agent_name": "heavi-chat",
        "event_type": "user_message",
        "content": f"hello from {session_id}",
        "session_id": session_id,
    }
    if user_id is not None:
        event["user_id"] = user_id
    if user_name is not None:
        event["user_name"] = user_name
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
    assert workspace["end_user_notepads_folder_id"] is not None

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


# --- The user write contract ---


@pytest.mark.asyncio
async def test_user_upload_creates_end_user_and_stamps_session(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(
        client,
        machine_key,
        [_event("sess-riverside-1", user_id="org_riverside", user_name="Riverside Truck")],
    )

    end_user = await pool.fetchrow(
        "SELECT * FROM end_users WHERE workspace_id = $1 AND external_id = 'org_riverside'",
        uuid.UUID(workspace["id"]),
    )
    assert end_user is not None
    assert end_user["name"] == "Riverside Truck"
    assert end_user["share_wiki"] is True
    assert end_user["notepad_folder_id"] is not None

    session = await pool.fetchrow(
        "SELECT end_user_id FROM sessions WHERE owner_user_id = $1 AND session_id = 'sess-riverside-1'",
        uuid.UUID(workspace["scope_user_id"]),
    )
    assert session["end_user_id"] == end_user["id"]


@pytest.mark.asyncio
async def test_one_user_appends_to_their_session_across_batches(client: AsyncClient, pool):
    """The ordinary case the collision guard must not break: a customer's agent
    pushes turn after turn under the same session id, and they accumulate in one
    session belonging to that customer."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    for _ in range(3):
        await _push(client, machine_key, [_event("sess-sticky", user_id="org_a", user_name="A")])

    rows = await pool.fetch(
        "SELECT eu.external_id FROM sessions s JOIN end_users eu ON eu.id = s.end_user_id "
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
async def test_user_upload_on_personal_scope_fails_loud(client: AsyncClient):
    api_key, _ = await _register_with_email(client, f"{unique_name('solo')}@example.com")
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("sess-1", user_id="org_x")]},
        headers=_auth(api_key),
    )
    assert resp.status_code == 400
    assert "workspace" in resp.json()["detail"]


# --- The user read contract (VFS) ---


@pytest.mark.asyncio
async def test_user_vfs_isolates_users(client: AsyncClient, pool):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(
        client,
        machine_key,
        [
            _event("sess-acme-1", user_id="org_acme", user_name="Acme"),
            _event("sess-beta-1", user_id="org_beta", user_name="Beta"),
            _event("sess-internal"),
        ],
    )

    # Seed a wiki page (shared) and a page in each user's notepad.
    end_users = {
        r["external_id"]: r
        for r in await pool.fetch(
            "SELECT external_id, notepad_folder_id FROM end_users WHERE workspace_id = $1",
            uuid.UUID(workspace["id"]),
        )
    }
    scope_id = uuid.UUID(workspace["scope_user_id"])
    for name, folder_id in [
        ("Fault codes", uuid.UUID(workspace["external_wiki_folder_id"])),
        ("Acme notes", end_users["org_acme"]["notepad_folder_id"]),
        ("Beta notes", end_users["org_beta"]["notepad_folder_id"]),
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
        json={"script": "find / -type f", "user_id": "org_acme"},
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
async def test_new_user_reads_the_shared_wiki_before_they_have_written(client: AsyncClient, pool):
    """A customer's agent reads context before it records anything, so its very
    first call names a user that has no row yet. That has to work, and it has to
    return the shared wiki: the accumulated cross-user knowledge is exactly what
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
        json={"script": "find / -type f", "user_id": "org_never_seen"},
        headers=_auth(machine_key),
    )
    assert resp.status_code == 200, resp.text
    listing = resp.json()["stdout"]
    assert "Fault codes" in listing
    # It owns nothing yet — no notepad, no sessions of its own.
    assert "notepad" not in listing


@pytest.mark.asyncio
async def test_legacy_tenant_id_field_fails_loud(client: AsyncClient):
    """A caller still sending the pre-rename tenant_id must get a 422, not
    silence. Dropped on an upload it records events with no user attached;
    dropped on a VFS read it runs unscoped — the whole workspace instead of
    one user's view."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    upload = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "heavi-chat",
                    "event_type": "user_message",
                    "content": "hi",
                    "session_id": "s1",
                    "tenant_id": "org_acme",
                }
            ]
        },
        headers=_auth(machine_key),
    )
    assert upload.status_code == 422

    read = await client.post(
        "/api/v1/me/vfs",
        json={"script": "ls /", "tenant_id": "org_acme"},
        headers=_auth(machine_key),
    )
    assert read.status_code == 422


@pytest.mark.asyncio
async def test_session_id_with_a_slash_round_trips(client: AsyncClient):
    """Session ids are the developer's own strings — slashes included. They
    used to be refused because the id was a path parameter on the transcript
    endpoints; those take it as a query parameter now, so the whole write →
    read-back loop must work with a slash in the id."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    ok = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("acme/conv-1", user_id="org_a", user_name="A")]},
        headers=_auth(machine_key),
    )
    assert ok.status_code == 201, ok.text

    events = await client.get(
        "/api/v1/me/transcripts/events",
        params={"session_id": "acme/conv-1", "limit": 100},
        headers=_auth(machine_key),
    )
    assert events.status_code == 200, events.text
    assert "hello from acme/conv-1" in str(events.json())


@pytest.mark.asyncio
async def test_two_users_cannot_share_a_session_id(client: AsyncClient, pool):
    """Session ids come from the developer's own app, so two of their customers
    picking the same one is ordinary. Sessions are unique on (owner, session_id)
    and the owner is the workspace, so appending regardless files one customer's
    turn inside another customer's transcript — where that customer's agent can
    read it. This is the isolation the whole feature promises."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)

    await _push(client, machine_key, [_event("conv-1", user_id="org_one", user_name="One")])

    collision = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": [_event("conv-1", user_id="org_two", user_name="Two")]},
        headers=_auth(machine_key),
    )
    assert collision.status_code == 400
    assert "conv-1" in collision.json()["detail"]

    # Refused before anything was stored: the first customer's session holds
    # only its own turn, and the second customer has no session at all.
    rows = await pool.fetch(
        "SELECT eu.external_id FROM sessions s JOIN end_users eu ON eu.id = s.end_user_id "
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
async def test_console_lists_users_with_counts(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s1", user_id="org_acme", user_name="Acme"),
            _event("s2", user_id="org_acme", user_name="Acme"),
        ],
    )

    resp = await client.get(
        "/api/v1/me/users",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    users = resp.json()["users"]
    assert len(users) == 1
    assert users[0]["external_id"] == "org_acme"
    assert users[0]["session_count"] == 2


@pytest.mark.asyncio
async def test_console_wiki_opt_out(client: AsyncClient):
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(client, machine_key, [_event("s1", user_id="org_acme", user_name="Acme")])

    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}
    end_user = (await client.get("/api/v1/me/users", headers=scope)).json()["users"][0]

    resp = await client.patch(
        f"/api/v1/me/users/{end_user['id']}", json={"share_wiki": False}, headers=scope
    )
    assert resp.status_code == 200
    assert resp.json()["share_wiki"] is False

    # A member of a different workspace can't touch it.
    other_key, _, other_ws = await _developer(client)
    resp = await client.patch(
        f"/api/v1/me/users/{end_user['id']}",
        json={"share_wiki": True},
        headers={**_auth(other_key), "X-Stash-Scope": other_ws["scope_user_id"]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_console_sessions_labelled_by_user(client: AsyncClient):
    """The console's sessions list is the cross-user view: every session the
    workspace recorded, each carrying its user label — and user-less rows
    (the workspace's own agents) still listed rather than hidden."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s-acme", user_id="org_acme", user_name="Acme"),
            _event("s-beta", user_id="org_beta", user_name="Beta"),
            _event("s-internal"),
        ],
    )

    resp = await client.get(
        "/api/v1/me/developer/sessions",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    rows = {r["session_id"]: r for r in resp.json()["sessions"]}
    assert rows["s-acme"]["user_name"] == "Acme"
    assert rows["s-beta"]["user_external_id"] == "org_beta"
    assert rows["s-internal"]["user_id"] is None
    assert rows["s-acme"]["event_count"] == 1


@pytest.mark.asyncio
async def test_console_files_split_by_wiki_and_user(client: AsyncClient, pool):
    """The files view answers 'whose is this?' by construction: shared wiki
    material in one pile, each user's own pages in theirs — never mixed."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s-acme", user_id="org_acme", user_name="Acme"),
            _event("s-beta", user_id="org_beta", user_name="Beta"),
        ],
    )
    end_users = {
        r["external_id"]: r
        for r in await pool.fetch(
            "SELECT external_id, notepad_folder_id FROM end_users WHERE workspace_id = $1",
            uuid.UUID(workspace["id"]),
        )
    }
    scope_id = uuid.UUID(workspace["scope_user_id"])
    for name, folder_id in [
        ("Fault codes", uuid.UUID(workspace["external_wiki_folder_id"])),
        ("Acme notes", end_users["org_acme"]["notepad_folder_id"]),
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
    by_user = {u["external_id"]: u for u in body["users"]}
    assert [p["name"] for p in by_user["org_acme"]["notepad_pages"]] == ["Acme notes"]
    assert by_user["org_beta"]["notepad_pages"] == []


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
        json={"instructions": "Never share pricing between users."},
        headers=scope,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["instructions"] == "Never share pricing between users."

    resp = await client.get("/api/v1/me/developer/curator", headers=scope)
    assert resp.json()["instructions"] == "Never share pricing between users."

    resp = await client.patch(
        "/api/v1/me/developer/curator", json={"instructions": ""}, headers=scope
    )
    assert resp.status_code == 200
    assert resp.json()["instructions"] is None


@pytest.mark.asyncio
async def test_backfill_dispatches_full_history_without_touching_watermark(
    client: AsyncClient, monkeypatch
):
    """Backfill means 'read everything again' — but only the run itself works
    from the empty watermark. The stored watermark must survive the dispatch
    untouched: a failed or lost backfill run must not have thrown away the
    incremental position."""
    from backend.tasks import agent_schedules

    dispatched: list[tuple] = []
    monkeypatch.setattr(
        agent_schedules.run_curator_now,
        "delay",
        lambda *args, **kwargs: dispatched.append((args, kwargs)),
    )

    api_key, _, workspace = await _developer(client)
    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}

    # Creating the curator seeds a bounded-backfill watermark.
    resp = await client.get("/api/v1/me/developer/curator", headers=scope)
    watermark = resp.json()["curator"]["curated_through"]
    assert watermark is not None

    resp = await client.post("/api/v1/me/developer/curator/backfill", headers=scope)
    assert resp.status_code == 202, resp.text
    assert len(dispatched) == 1
    assert dispatched[0][1] == {"full_history": True}

    resp = await client.get("/api/v1/me/developer/curator", headers=scope)
    assert resp.json()["curator"]["curated_through"] == watermark


@pytest.mark.asyncio
async def test_user_wiki_graph(client: AsyncClient, pool):
    """A user's own wiki renders as a graph like the shared one — and only
    theirs: another user's pages must not leak into it."""
    api_key, _, workspace = await _developer(client)
    machine_key = await _mint_workspace_key(client, api_key, workspace)
    await _push(
        client,
        machine_key,
        [
            _event("s-acme", user_id="org_acme", user_name="Acme"),
            _event("s-beta", user_id="org_beta", user_name="Beta"),
        ],
    )
    end_users = {
        r["external_id"]: r
        for r in await pool.fetch(
            "SELECT id, external_id, notepad_folder_id FROM end_users WHERE workspace_id = $1",
            uuid.UUID(workspace["id"]),
        )
    }
    scope_id = uuid.UUID(workspace["scope_user_id"])
    for name, folder_id in [
        ("Acme notes", end_users["org_acme"]["notepad_folder_id"]),
        ("Beta notes", end_users["org_beta"]["notepad_folder_id"]),
    ]:
        await pool.execute(
            "INSERT INTO pages (owner_user_id, name, content_markdown, folder_id, created_by) "
            "VALUES ($1, $2, 'body', $3, $1)",
            scope_id,
            name,
            folder_id,
        )

    resp = await client.get(
        f"/api/v1/me/users/{end_users['org_acme']['id']}/wiki-graph",
        headers={**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]},
    )
    assert resp.status_code == 200, resp.text
    names = [n["name"] for n in resp.json()["nodes"]]
    assert "Acme notes" in names
    assert "Beta notes" not in names


@pytest.mark.asyncio
async def test_key_expiry(client: AsyncClient, pool):
    """A key minted with expires_in_days works until the stamp passes, then is
    refused with "expired" — not "invalid": the developer debugging a dead
    integration must learn the key aged out, not think it was deleted."""
    api_key, _, workspace = await _developer(client)
    scope = {**_auth(api_key), "X-Stash-Scope": workspace["scope_user_id"]}

    resp = await client.post(
        "/api/v1/me/developer/keys",
        json={"name": "short-lived", "access": "read", "expires_in_days": 7},
        headers=scope,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["expires_at"] is not None
    minted = resp.json()["api_key"]

    listed = (await client.get("/api/v1/me/developer/keys", headers=scope)).json()["keys"]
    assert listed[0]["name"] == "short-lived"
    assert listed[0]["expires_at"] is not None

    ok = await client.post("/api/v1/me/vfs", json={"script": "ls /"}, headers=_auth(minted))
    assert ok.status_code == 200, ok.text

    await pool.execute(
        "UPDATE user_api_keys SET expires_at = now() - interval '1 minute' WHERE id = $1",
        uuid.UUID(listed[0]["id"]),
    )
    denied = await client.post("/api/v1/me/vfs", json={"script": "ls /"}, headers=_auth(minted))
    assert denied.status_code == 401
    assert "expired" in denied.json()["detail"]


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
