"""Multiplier: input-side consent for team learning.

What matters here:
- The master upload switch rejects loudly (403), never drops silently.
- Raw transcripts are NEVER team-readable — a workspace co-member sees a
  teammate's session only via an explicit per-person share.
- Every member session feeds the team curator's inputs BY DEFAULT; the
  per-session exclusion is the escape hatch, flippable only by the owner.
- Team analytics stay metadata-only.
"""

import uuid

import pytest
from httpx import AsyncClient

from backend.services import curation_service

from .conftest import unique_name
from .test_permissions import _auth, _register_with_email
from .test_workspaces import ADMIN, _create_workspace, _verify_email


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    monkeypatch.setattr("backend.routers.admin.settings.ADMIN_PASSWORD", ADMIN["X-Admin-Token"])


def _domain() -> str:
    return f"{unique_name('team')}.com".lower()


async def _member(client: AsyncClient, pool, domain: str) -> tuple[str, dict]:
    key, body = await _register_with_email(client, f"{unique_name('u')}@{domain}")
    await _verify_email(pool, uuid.UUID(body["id"]))
    return key, body


async def _push_event(client: AsyncClient, key: str, session_id: str, content: str) -> int:
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "tester",
            "event_type": "user_message",
            "content": content,
            "session_id": session_id,
        },
        headers=_auth(key),
    )
    return resp.status_code


# --- The master upload switch (Idea 9) ---


@pytest.mark.asyncio
async def test_upload_switch_rejects_loudly_and_reversibly(client: AsyncClient):
    key, _ = await _register_with_email(client, f"{unique_name('solo')}@example.com")

    resp = await client.patch(
        "/api/v1/users/me", json={"session_uploads_enabled": False}, headers=_auth(key)
    )
    assert resp.status_code == 200
    assert resp.json()["session_uploads_enabled"] is False

    assert await _push_event(client, key, "sess-blocked", "nope") == 403
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "tester",
                    "event_type": "user_message",
                    "content": "nope",
                    "session_id": "sess-blocked",
                }
            ]
        },
        headers=_auth(key),
    )
    assert resp.status_code == 403

    await client.patch(
        "/api/v1/users/me", json={"session_uploads_enabled": True}, headers=_auth(key)
    )
    assert await _push_event(client, key, "sess-open", "hello") == 201


# --- Raw traces never leak to the team ---


@pytest.mark.asyncio
async def test_raw_sessions_are_never_team_readable(client: AsyncClient, pool):
    domain = _domain()
    await _create_workspace(client, domain)
    owner_key, _ = await _member(client, pool, domain)
    teammate_key, _ = await _member(client, pool, domain)

    assert await _push_event(client, owner_key, "sess-raw", "my private words") == 201

    # In team memory by default — and STILL not readable by a co-member:
    # participation feeds the distillation, never the transcript.
    resp = await client.get("/api/v1/me/sessions/sess-raw", headers=_auth(owner_key))
    assert resp.status_code == 200
    assert resp.json()["team_memory_excluded"] is False

    resp = await client.get("/api/v1/sessions/sess-raw", headers=_auth(teammate_key))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_explicit_share_still_grants_a_teammate_the_transcript(client: AsyncClient, pool):
    domain = _domain()
    await _create_workspace(client, domain)
    owner_key, owner = await _member(client, pool, domain)
    teammate_key, teammate = await _member(client, pool, domain)

    assert await _push_event(client, owner_key, "sess-handoff", "context for you") == 201
    session = (
        await client.get("/api/v1/me/sessions/sess-handoff", headers=_auth(owner_key))
    ).json()

    email = await pool.fetchval("SELECT email FROM users WHERE id = $1", uuid.UUID(teammate["id"]))
    resp = await client.post(
        "/api/v1/share",
        json={"object_type": "session", "object_id": session["id"], "email": email},
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/sessions/sess-handoff", headers=_auth(teammate_key))
    assert resp.status_code == 200


# --- Per-session exclusion (the opt-out) ---


@pytest.mark.asyncio
async def test_only_the_owner_can_flip_exclusion(client: AsyncClient, pool):
    domain = _domain()
    await _create_workspace(client, domain)
    owner_key, _ = await _member(client, pool, domain)
    teammate_key, _ = await _member(client, pool, domain)

    assert await _push_event(client, owner_key, "sess-mine", "mine") == 201

    resp = await client.patch(
        "/api/v1/me/sessions/sess-mine/team-memory",
        json={"excluded": True},
        headers=_auth(teammate_key),
    )
    assert resp.status_code == 404  # not their session, not their call

    resp = await client.patch(
        "/api/v1/me/sessions/sess-mine/team-memory",
        json={"excluded": True},
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200
    assert resp.json()["team_memory_excluded"] is True


# --- The team curator's inputs (opt-out semantics) ---


@pytest.mark.asyncio
async def test_workspace_curator_feed_default_in_exclusion_respected(client: AsyncClient, pool):
    domain = _domain()
    ws = await _create_workspace(client, domain)
    scope_user_id = uuid.UUID(ws["scope_user_id"])
    owner_key, owner = await _member(client, pool, domain)

    assert await _push_event(client, owner_key, "sess-default-in", "a work learning") == 201
    assert await _push_event(client, owner_key, "sess-opted-out", "keep this out") == 201
    resp = await client.patch(
        "/api/v1/me/sessions/sess-opted-out/team-memory",
        json={"excluded": True},
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200

    delta = await curation_service.changes_since(scope_user_id, scope_user_id, None)
    feed_sessions = {e["session_id"] for e in delta["history"]}
    assert "sess-default-in" in feed_sessions  # participates without any action
    assert "sess-opted-out" not in feed_sessions  # exclusion is honored
    default_event = next(e for e in delta["history"] if e["session_id"] == "sess-default-in")
    assert default_event["author"] == owner["display_name"]

    # The cheap gate agrees with the feed.
    epoch = await pool.fetchval("SELECT now() - interval '1 day'")
    assert await curation_service.has_changes_since(scope_user_id, scope_user_id, epoch)

    # The owner's PERSONAL curator still sees both — exclusion is a team
    # boundary, not a personal one.
    personal = await curation_service.changes_since(
        uuid.UUID(owner["id"]), uuid.UUID(owner["id"]), None
    )
    personal_sessions = {e["session_id"] for e in personal["history"]}
    assert {"sess-default-in", "sess-opted-out"} <= personal_sessions


# --- Team endpoints ---


@pytest.mark.asyncio
async def test_team_membership_and_metadata_only_analytics(client: AsyncClient, pool):
    domain = _domain()
    await _create_workspace(client, domain)
    owner_key, owner = await _member(client, pool, domain)
    teammate_key, _ = await _member(client, pool, domain)
    loner_key, _ = await _register_with_email(client, f"{unique_name('l')}@nowhere.com")

    assert await _push_event(client, owner_key, "sess-a", "learning one") == 201
    assert await _push_event(client, owner_key, "sess-b", "keep out") == 201
    await client.patch(
        "/api/v1/me/sessions/sess-b/team-memory",
        json={"excluded": True},
        headers=_auth(owner_key),
    )

    resp = await client.get("/api/v1/me/team", headers=_auth(teammate_key))
    assert resp.status_code == 200
    member_ids = {m["id"] for m in resp.json()["members"]}
    assert owner["id"] in member_ids and len(member_ids) >= 2

    resp = await client.get("/api/v1/me/team/analytics", headers=_auth(teammate_key))
    assert resp.status_code == 200
    owner_row = next(m for m in resp.json()["members"] if m["id"] == owner["id"])
    assert owner_row["sessions_total"] == 2
    assert owner_row["est_tokens_30d"] > 0
    # Metadata only — and deliberately NO exclusion counts: teammates seeing
    # who opts out how often would pressure people away from the escape hatch.
    assert set(owner_row) == {
        "id",
        "name",
        "display_name",
        "sessions_total",
        "sessions_7d",
        "sessions_30d",
        "est_tokens_30d",
        "last_session_at",
    }

    resp = await client.get("/api/v1/me/team", headers=_auth(loner_key))
    assert resp.status_code == 404


# --- Provenance: honest opt-out + the enforced skills bar ---


@pytest.mark.asyncio
async def test_exclusion_flags_derived_pages_and_curator_sees_rebuild_orders(
    client: AsyncClient, pool
):
    domain = _domain()
    ws = await _create_workspace(client, domain)
    scope = ws["scope_user_id"]
    owner_key, owner = await _member(client, pool, domain)

    assert await _push_event(client, owner_key, "sess-src", "the learning") == 201

    # A team wiki page recorded as built from that session.
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": "Derived learning",
            "content": "distilled",
            "source_sessions": [
                {"owner_user_id": owner["id"], "session_id": "sess-src"}
            ],
        },
        headers={**_auth(owner_key), "X-Stash-Scope": scope},
    )
    assert resp.status_code == 201, resp.text
    page_id = resp.json()["id"]

    # The owner opts the session out — the derived page is flagged, and the
    # response says so.
    resp = await client.patch(
        "/api/v1/me/sessions/sess-src/team-memory",
        json={"excluded": True},
        headers=_auth(owner_key),
    )
    assert resp.status_code == 200
    assert resp.json()["pages_flagged"] == 1

    flagged = await pool.fetchval(
        "SELECT needs_recuration FROM pages WHERE id = $1", uuid.UUID(page_id)
    )
    assert flagged is True

    # The workspace curator's delta carries the rebuild order.
    delta = await curation_service.changes_since(
        uuid.UUID(scope), uuid.UUID(scope), None
    )
    assert any(p["id"] == page_id for p in delta["stale_pages"])
    epoch = await pool.fetchval("SELECT now() - interval '1 day'")
    assert await curation_service.has_changes_since(
        uuid.UUID(scope), uuid.UUID(scope), epoch
    )

    # A rebuild that restates sources clears the flag.
    resp = await client.patch(
        f"/api/v1/me/pages/{page_id}",
        json={"content": "rebuilt without it", "source_sessions": []},
        headers={**_auth(owner_key), "X-Stash-Scope": scope},
    )
    assert resp.status_code == 200, resp.text
    flagged = await pool.fetchval(
        "SELECT needs_recuration FROM pages WHERE id = $1", uuid.UUID(page_id)
    )
    assert flagged is False


@pytest.mark.asyncio
async def test_team_skills_bar_is_enforced_at_write_time(client: AsyncClient, pool):
    domain = _domain()
    ws = await _create_workspace(client, domain)
    scope = ws["scope_user_id"]
    author_a_key, author_a = await _member(client, pool, domain)
    _, author_b = await _member(client, pool, domain)

    assert await _push_event(client, author_a_key, "sess-a1", "pattern") == 201

    resp = await client.get("/api/v1/me/team/skills", headers=_auth(author_a_key))
    assert resp.status_code == 200
    skills_folder = resp.json()["folder_id"]

    # One author's sessions: rejected loudly.
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": "One-person pattern",
            "content": "not yet a team skill",
            "folder_id": skills_folder,
            "source_sessions": [
                {"owner_user_id": author_a["id"], "session_id": "sess-a1"}
            ],
        },
        headers={**_auth(author_a_key), "X-Stash-Scope": scope},
    )
    assert resp.status_code == 422

    # No sources at all: also rejected.
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "Sourceless", "content": "no", "folder_id": skills_folder},
        headers={**_auth(author_a_key), "X-Stash-Scope": scope},
    )
    assert resp.status_code == 422

    # Two distinct authors: accepted.
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={
            "name": "Real team skill",
            "content": "do it this way",
            "folder_id": skills_folder,
            "source_sessions": [
                {"owner_user_id": author_a["id"], "session_id": "sess-a1"},
                {"owner_user_id": author_b["id"], "session_id": "sess-b1"},
            ],
        },
        headers={**_auth(author_a_key), "X-Stash-Scope": scope},
    )
    assert resp.status_code == 201, resp.text

    # Personal scopes are untouched by the bar.
    resp = await client.post(
        "/api/v1/me/pages/new",
        json={"name": "My own note", "content": "mine"},
        headers=_auth(author_a_key),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_new_workspace_gets_a_curator(client: AsyncClient, pool):
    ws = await _create_workspace(client, _domain())
    row = await pool.fetchrow(
        "SELECT run_mode, schedule_cron FROM agents WHERE user_id = $1 AND is_curator",
        uuid.UUID(ws["scope_user_id"]),
    )
    assert row is not None
    assert row["run_mode"] == "scheduled"
    assert row["schedule_cron"]
