"""Backend coverage for the rows-only transcript path.

Upload now parses JSONL into history_events rows; no R2 blob. The
roundtrip test confirms the events come back out of the /events
endpoint in the shape the session viewer can parse.
"""

import io
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient

from .conftest import unique_name

BODY = (
    json.dumps({"type": "user", "message": {"content": "hi"}, "timestamp": "2026-05-10T20:00:00Z"})
    + "\n"
    + json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hello"}]},
            "timestamp": "2026-05-10T20:00:01Z",
        }
    )
    + "\n"
).encode()


async def _register_user(client) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    assert r.status_code == 201
    body = r.json()
    return body["api_key"], body["id"]


async def _register(client):
    key, _user_id = await _register_user(client)
    return key


async def _share(pool, scope, object_type, object_id, user_id, owner_id, permission="read"):
    await pool.execute(
        "INSERT INTO shares (owner_user_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1, $2, $3, 'user', $4, $5, $6)",
        UUID(scope),
        object_type,
        object_id,
        UUID(user_id),
        permission,
        UUID(owner_id),
    )


async def _scope(client, key):
    r = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200
    return r.json()["id"]


@pytest.mark.asyncio
async def test_upload_inserts_events_and_events_roundtrip(client: AsyncClient):
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}

    up = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-1", "agent_name": "claude"},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    payload = up.json()
    assert payload["imported"] == 2
    assert payload["skipped"] is False

    meta = await client.get(
        "/api/v1/me/transcripts?session_id=sess-1",
        headers=headers,
    )
    assert meta.status_code == 200
    assert meta.json()["event_count"] == 2

    events_resp = await client.get(
        "/api/v1/me/transcripts/events",
        params={"session_id": "sess-1", "limit": 100},
        headers=headers,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    assert [event["role"] for event in events] == ["user", "assistant"]
    assert events[0]["content"] == "hi"
    assert events[1]["content"] == "hello"


@pytest.mark.asyncio
async def test_events_endpoint_requires_an_explicit_limit(client: AsyncClient):
    """limit is required, with no server-side default. A default is invisible
    to the caller: a short response is indistinguishable from a short session,
    which is precisely how every long transcript came to be rendered silently
    cut off. Refusing the bare request forces the caller to choose a count, and
    a caller that chose one can disclose what it left out."""
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}

    turns = 150
    body = (
        "\n".join(
            json.dumps(
                {
                    "type": "user",
                    "message": {"content": f"msg-{i}"},
                    "timestamp": f"2026-05-10T20:00:00.{i:03d}Z",
                }
            )
            for i in range(turns)
        )
        + "\n"
    ).encode()
    up = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(body), "application/jsonl")},
        data={"session_id": "sess-unpaged", "agent_name": "claude"},
        headers=headers,
    )
    assert up.status_code == 201, up.text

    bare = await client.get(
        "/api/v1/me/transcripts/events?session_id=sess-unpaged", headers=headers
    )
    assert bare.status_code == 422

    # A limit past the end of the session is not an error — it is how a caller
    # asks for the whole thing and learns that it got it.
    whole = await client.get(
        "/api/v1/me/transcripts/events",
        params={"session_id": "sess-unpaged", "limit": turns * 2},
        headers=headers,
    )
    assert whole.status_code == 200
    payload = whole.json()
    assert payload["total"] == turns
    assert payload["has_more"] is False
    assert len(payload["events"]) == turns
    assert payload["events"][-1]["content"] == f"msg-{turns - 1}"


@pytest.mark.asyncio
async def test_events_endpoint_paginates(client: AsyncClient):
    """The viewer loads the transcript a page at a time. offset is a turn
    ordinal, total is the full turn count, and has_more drives infinite scroll —
    so a long session never loads every event up front."""
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}

    body = (
        "\n".join(
            json.dumps(
                {
                    "type": "user",
                    "message": {"content": f"msg-{i}"},
                    "timestamp": f"2026-05-10T20:00:0{i}Z",
                }
            )
            for i in range(5)
        )
        + "\n"
    ).encode()
    up = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(body), "application/jsonl")},
        data={"session_id": "sess-page", "agent_name": "claude"},
        headers=headers,
    )
    assert up.status_code == 201, up.text

    first = await client.get(
        "/api/v1/me/transcripts/events",
        params={"session_id": "sess-page", "limit": 2, "offset": 0},
        headers=headers,
    )
    assert first.status_code == 200
    page = first.json()
    assert page["total"] == 5
    assert page["has_more"] is True
    assert [e["content"] for e in page["events"]] == ["msg-0", "msg-1"]

    last = await client.get(
        "/api/v1/me/transcripts/events",
        params={"session_id": "sess-page", "limit": 2, "offset": 4},
        headers=headers,
    )
    assert last.status_code == 200
    tail = last.json()
    assert tail["total"] == 5
    assert tail["has_more"] is False
    assert [e["content"] for e in tail["events"]] == ["msg-4"]


@pytest.mark.asyncio
async def test_reupload_is_noop_when_events_exist(client: AsyncClient):
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}

    first = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-dup", "agent_name": "claude"},
        headers=headers,
    )
    assert first.status_code == 201
    assert first.json()["imported"] == 2

    second = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-dup", "agent_name": "claude"},
        headers=headers,
    )
    assert second.status_code == 201
    assert second.json()["skipped"] is True
    assert second.json()["imported"] == 0


@pytest.mark.asyncio
async def test_empty_session_shell_is_hidden_from_default_views(client: AsyncClient):
    key = await _register(client)
    scope = await _scope(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "empty-shell", "agent_name": "claude"},
        headers=headers,
    )
    assert created.status_code == 201

    overview = await client.get("/api/v1/me/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["sessions"] == []

    sidebar = await client.get("/api/v1/me/sidebar", headers=headers)
    assert sidebar.status_code == 200
    assert sidebar.json()["sessions"] == []

    my_sessions = await client.get(
        "/api/v1/me/sessions",
        params={"owner_user_id": scope},
        headers=headers,
    )
    assert my_sessions.status_code == 200
    assert my_sessions.json()["sessions"] == []

    detail = await client.get(
        "/api/v1/me/sessions/detail?session_id=empty-shell",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["session_id"] == "empty-shell"


@pytest.mark.asyncio
async def test_event_creates_the_session_row(client: AsyncClient):
    """An agent with no session-start hook (e.g. Codex) creates its session row
    from the first pushed event, so the session must appear in the list even
    though nothing called the session endpoint."""
    key = await _register(client)
    scope = await _scope(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    pushed = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "codex",
            "event_type": "assistant_message",
            "content": "untargeted session",
            "session_id": "codex-untargeted",
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    listed = await client.get(
        "/api/v1/me/sessions", params={"owner_user_id": scope}, headers=headers
    )
    assert listed.status_code == 200
    assert any(s["session_id"] == "codex-untargeted" for s in listed.json()["sessions"])


@pytest.mark.asyncio
async def test_replace_reimports_existing_session(client: AsyncClient):
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}
    replacement = (
        json.dumps(
            {
                "type": "user",
                "message": {"content": "updated"},
                "timestamp": "2026-05-10T20:00:02Z",
            }
        )
        + "\n"
    ).encode()

    first = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-replace", "agent_name": "claude"},
        headers=headers,
    )
    assert first.status_code == 201
    assert first.json()["imported"] == 2

    second = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(replacement), "application/jsonl")},
        data={"session_id": "sess-replace", "agent_name": "claude", "replace": "true"},
        headers=headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["skipped"] is False
    assert second.json()["imported"] == 1

    events_resp = await client.get(
        "/api/v1/me/transcripts/events",
        params={"session_id": "sess-replace", "limit": 100},
        headers=headers,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    assert [event["content"] for event in events] == ["updated"]


@pytest.mark.asyncio
async def test_sidebar_sessions_include_human_author(client: AsyncClient):
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    author = me.json()["display_name"]

    pushed = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "claude",
                    "event_type": "user_message",
                    "content": "Plan the release",
                    "session_id": "sess-human-author",
                }
            ]
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    overview = await client.get("/api/v1/me/overview", headers=headers)
    assert overview.status_code == 200
    [overview_session] = overview.json()["sessions"]
    assert overview_session["user_name"] == author
    assert overview_session["agent_name"] == "claude"

    sidebar = await client.get("/api/v1/me/sidebar", headers=headers)
    assert sidebar.status_code == 200
    [sidebar_session] = sidebar.json()["sessions"]
    assert sidebar_session["user_name"] == author
    assert sidebar_session["agent_name"] == "claude"
    etag = sidebar.headers["etag"]

    updated = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "claude",
                    "event_type": "assistant_message",
                    "content": "Release plan is ready",
                    "session_id": "sess-human-author",
                    "created_at": "2026-05-10T20:00:01Z",
                }
            ]
        },
        headers=headers,
    )
    assert updated.status_code == 201

    refreshed = await client.get(
        "/api/v1/me/sidebar",
        headers={**headers, "If-None-Match": etag},
    )
    assert refreshed.status_code == 200
    assert refreshed.headers["etag"] != etag


@pytest.mark.asyncio
async def test_agent_name_matching_author_handle_is_suppressed(client: AsyncClient):
    """The CLI plugin historically defaulted agent_name to the author's login
    handle, so those rows name a person, not an agent. The session lists must
    not present a person as the agent — the value is suppressed instead."""
    key = await _register(client)
    scope = await _scope(client, key)
    headers = {"Authorization": f"Bearer {key}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    handle = me.json()["name"]

    pushed = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": handle,
                    "event_type": "user_message",
                    "content": "Plan the release",
                    "session_id": "sess-handle-agent",
                }
            ]
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    mine = await client.get(f"/api/v1/me/sessions?owner_user_id={scope}", headers=headers)
    assert mine.status_code == 200
    assert mine.json()["sessions"][0]["agent_name"] is None

    overview = await client.get("/api/v1/me/overview", headers=headers)
    assert overview.status_code == 200
    [overview_session] = overview.json()["sessions"]
    assert overview_session["agent_name"] == ""


@pytest.mark.asyncio
async def test_sidebar_etag_changes_after_generated_title(
    client: AsyncClient,
    pool,
):
    key = await _register(client)
    scope = await _scope(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    pushed = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "codex",
                    "event_type": "user_message",
                    "content": "Please make the release checklist easier to scan.",
                    "session_id": "sess-generated-title",
                    "created_at": "2026-05-10T20:00:00Z",
                }
            ]
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    sidebar = await client.get("/api/v1/me/sidebar", headers=headers)
    assert sidebar.status_code == 200
    etag = sidebar.headers["etag"]
    [fallback_session] = sidebar.json()["sessions"]
    assert fallback_session["title"] == "Make the release checklist easier to scan"

    await pool.execute(
        """
        UPDATE sessions SET
          title = $3,
          title_source_hash = $4,
          title_updated_at = now()
        WHERE owner_user_id = $1 AND session_id = $2
        """,
        UUID(scope),
        "sess-generated-title",
        "Release Checklist Readability",
        "test-source-hash",
    )

    refreshed = await client.get(
        "/api/v1/me/sidebar",
        headers={**headers, "If-None-Match": etag},
    )
    assert refreshed.status_code == 200
    assert refreshed.headers["etag"] != etag
    [generated_session] = refreshed.json()["sessions"]
    assert generated_session["title"] == "Release Checklist Readability"


@pytest.mark.asyncio
async def test_session_detail_returns_files_touched_and_artifacts_list(client: AsyncClient):
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        "/api/v1/me/sessions",
        json={
            "session_id": "sess-files",
            "agent_name": "codex",
            "files_touched": ["frontend/src/app/page.tsx", "backend/main.py"],
        },
        headers=headers,
    )
    assert created.status_code == 201

    detail = await client.get(
        "/api/v1/me/sessions/detail?session_id=sess-files",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["files_touched"] == [
        "frontend/src/app/page.tsx",
        "backend/main.py",
    ]
    assert detail.json()["artifacts"] == []


@pytest.mark.asyncio
async def test_session_purge_deletes_artifacts_from_storage(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "sess-purge", "agent_name": "codex"},
        headers=headers,
    )
    assert created.status_code == 201
    session_row_id = UUID(created.json()["id"])

    await pool.execute(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, $2, $3, $4)",
        session_row_id,
        "screenshots/home.png",
        "artifact-key",
        32,
    )

    deleted_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        deleted_keys.append(storage_key)

    monkeypatch.setattr("backend.routers.sessions.storage_service.delete_file", fake_delete_file)

    trashed = await client.delete(
        f"/api/v1/me/sessions/{session_row_id}",
        headers=headers,
    )
    assert trashed.status_code == 204

    purged = await client.delete(
        f"/api/v1/me/sessions/{session_row_id}/purge",
        headers=headers,
    )
    assert purged.status_code == 204
    assert deleted_keys == ["artifact-key"]
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
            session_row_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_session_purge_keeps_artifact_storage_keys_still_referenced(
    client: AsyncClient,
    pool,
    monkeypatch,
):
    key, user_id = await _register_user(client)
    scope = await _scope(client, key)
    owner_user_id = UUID(scope)
    user_uuid = UUID(user_id)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "sess-shared-artifacts", "agent_name": "codex"},
        headers=headers,
    )
    assert created.status_code == 201
    session_row_id = UUID(created.json()["id"])

    other_created = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "sess-other-artifacts", "agent_name": "codex"},
        headers=headers,
    )
    assert other_created.status_code == 201
    other_session_row_id = UUID(other_created.json()["id"])

    await pool.execute(
        "INSERT INTO files "
        "(owner_user_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        owner_user_id,
        "shared-file.pdf",
        "application/pdf",
        12,
        "shared-file-key",
        user_uuid,
    )
    for target_session_id, file_path, storage_key in [
        (session_row_id, "unique.txt", "unique-artifact-key"),
        (session_row_id, "shared-file.txt", "shared-file-key"),
        (session_row_id, "shared-session.txt", "shared-session-key"),
        (other_session_row_id, "shared-session.txt", "shared-session-key"),
    ]:
        await pool.execute(
            "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
            "VALUES ($1, $2, $3, $4)",
            target_session_id,
            file_path,
            storage_key,
            32,
        )

    deleted_keys: list[str] = []

    async def fake_delete_file(storage_key: str) -> None:
        deleted_keys.append(storage_key)

    monkeypatch.setattr("backend.routers.sessions.storage_service.delete_file", fake_delete_file)

    trashed = await client.delete(
        f"/api/v1/me/sessions/{session_row_id}",
        headers=headers,
    )
    assert trashed.status_code == 204

    purged = await client.delete(
        f"/api/v1/me/sessions/{session_row_id}/purge",
        headers=headers,
    )

    assert purged.status_code == 204
    assert deleted_keys == ["unique-artifact-key"]
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
            session_row_id,
        )
        == 0
    )
    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
            other_session_row_id,
        )
        == 1
    )
    assert (
        await pool.fetchval("SELECT COUNT(*) FROM files WHERE storage_key = $1", "shared-file-key")
        == 1
    )


@pytest.mark.asyncio
async def test_transcript_viewer_includes_streamed_legacy_event_types(client: AsyncClient):
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}

    pushed = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "codex",
                    "event_type": "prompt",
                    "content": "Please inspect the release.",
                    "session_id": "sess-streamed",
                    "created_at": "2026-05-10T20:00:00Z",
                },
                {
                    "agent_name": "codex",
                    "event_type": "assistant",
                    "content": "I found the relevant files.",
                    "session_id": "sess-streamed",
                    "created_at": "2026-05-10T20:00:01Z",
                },
                {
                    "agent_name": "codex",
                    "event_type": "tool_call",
                    "tool_name": "rg",
                    "content": "rg release",
                    "session_id": "sess-streamed",
                    "created_at": "2026-05-10T20:00:02Z",
                },
            ]
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    events_resp = await client.get(
        "/api/v1/me/transcripts/events",
        params={"session_id": "sess-streamed", "limit": 100},
        headers=headers,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    assert [event["role"] for event in events] == ["user", "assistant", "assistant"]
    assert [event["content"] for event in events] == [
        "Please inspect the release.",
        "I found the relevant files.",
        "rg release",
    ]


@pytest.mark.asyncio
async def test_oversize_rejected(client: AsyncClient):
    key = await _register(client)
    big = b"x" * (50 * 1024 * 1024 + 1)
    r = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(big), "application/jsonl")},
        data={"session_id": "sess-big", "agent_name": "claude"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_viewer_cannot_mutate_existing_session_artifacts_or_materialized_pages(
    client: AsyncClient,
    pool,
):
    owner_key, owner_id = await _register_user(client)
    viewer_key, viewer_id = await _register_user(client)
    scope = await _scope(client, owner_key)
    owner_headers = {"Authorization": f"Bearer {owner_key}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_key}"}

    created = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "owner-session", "agent_name": "codex"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    session_row_id = created.json()["id"]
    await _share(pool, scope, "session", UUID(session_row_id), viewer_id, owner_id)

    pushed = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "codex",
            "event_type": "assistant_message",
            "content": "owner content",
            "session_id": "owner-session",
        },
        headers=owner_headers,
    )
    assert pushed.status_code == 201

    artifact_resp = await client.post(
        f"/api/v1/me/sessions/{session_row_id}/artifacts",
        files={"file": ("artifact.txt", io.BytesIO(b"secret"), "text/plain")},
        data={"file_path": "artifact.txt"},
        headers=viewer_headers,
    )
    assert artifact_resp.status_code == 404

    folder_resp = await client.post(
        "/api/v1/me/folders",
        json={"name": "Materialized"},
        headers=owner_headers,
    )
    assert folder_resp.status_code == 201
    materialize_resp = await client.post(
        "/api/v1/me/sessions/materialize?session_id=owner-session",
        json={"folder_id": folder_resp.json()["id"]},
        headers=viewer_headers,
    )
    assert materialize_resp.status_code == 404

    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
            UUID(session_row_id),
        )
        == 0
    )
    assert await pool.fetchval("SELECT COUNT(*) FROM pages WHERE owner_user_id = $1", scope) == 0


@pytest.mark.asyncio
async def test_upload_dates_the_session_from_the_transcript(client: AsyncClient, pool):
    """A history import replays conversations from months ago. The session row
    must carry the transcript's own start time, not the moment of the import —
    otherwise every imported session sorts as if it happened today."""
    key = await _register(client)
    scope = await _scope(client, key)

    uploaded = await client.post(
        "/api/v1/me/transcripts",
        data={"session_id": "imported-old", "agent_name": "claude"},
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert uploaded.status_code == 201

    started_at = await pool.fetchval(
        "SELECT started_at FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
        scope,
        "imported-old",
    )
    # BODY's first event is 2026-05-10T20:00:00Z.
    assert started_at == datetime(2026, 5, 10, 20, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_live_session_is_dated_now(client: AsyncClient, pool):
    """A pushed event has no transcript to date it from, so the row's creation
    time is the session start. This is the path the transcript fix must not
    disturb."""
    key = await _register(client)
    scope = await _scope(client, key)

    pushed = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "claude",
            "event_type": "assistant_message",
            "content": "live",
            "session_id": "live-now",
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    assert pushed.status_code == 201

    started_at = await pool.fetchval(
        "SELECT started_at FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
        scope,
        "live-now",
    )
    assert (datetime.now(UTC) - started_at).total_seconds() < 60


@pytest.mark.asyncio
async def test_reupload_to_deleted_session_skips_without_resurrecting(client: AsyncClient, pool):
    """A history import that hits a session the user deleted must report a
    skip, not an error — and must not undelete the session."""
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}
    scope = await _scope(client, key)

    up = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-del", "agent_name": "claude"},
        headers=headers,
    )
    assert up.status_code == 201, up.text

    row_id = await pool.fetchval(
        "SELECT id FROM sessions WHERE owner_user_id = $1 AND session_id = $2",
        UUID(scope),
        "sess-del",
    )
    deleted = await client.delete(f"/api/v1/me/sessions/{row_id}", headers=headers)
    assert deleted.status_code == 204

    second = await client.post(
        "/api/v1/me/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-del", "agent_name": "claude"},
        headers=headers,
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["skipped"] is True
    assert body["reason"] == "session was deleted"

    assert (
        await pool.fetchval("SELECT deleted_at FROM sessions WHERE id = $1", row_id)
    ) is not None


@pytest.mark.asyncio
async def test_legacy_path_shapes_still_serve(client: AsyncClient):
    """Installed clients (released CLI, plugins, customer backends — Heavi's
    audit trail shows ~1.7k transcript reads a month over API keys) read by
    the old /{session_id} path shapes. The canonical routes moved the id to a
    query parameter; these aliases keep every old client working until the
    legacy cutover."""
    key = await _register(client)
    headers = {"Authorization": f"Bearer {key}"}
    up = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "claude",
                    "event_type": "user_message",
                    "content": "legacy shape check",
                    "session_id": "legacy-shape-1",
                }
            ]
        },
        headers=headers,
    )
    assert up.status_code == 201, up.text

    meta = await client.get("/api/v1/me/transcripts/legacy-shape-1", headers=headers)
    assert meta.status_code == 200, meta.text
    events = await client.get(
        "/api/v1/me/transcripts/legacy-shape-1/events", params={"limit": 10}, headers=headers
    )
    assert events.status_code == 200
    assert events.json()["events"][0]["content"] == "legacy shape check"
    export = await client.get("/api/v1/me/transcripts/legacy-shape-1/export.jsonl", headers=headers)
    assert export.status_code == 200
    detail = await client.get("/api/v1/me/sessions/legacy-shape-1", headers=headers)
    assert detail.status_code == 200
    renamed = await client.patch(
        "/api/v1/me/sessions/legacy-shape-1/title",
        json={"title": "Legacy shape check"},
        headers=headers,
    )
    assert renamed.status_code == 200
