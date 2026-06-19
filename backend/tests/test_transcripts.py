"""Backend coverage for the rows-only transcript path.

Upload now parses JSONL into history_events rows; no R2 blob. The
roundtrip test confirms the events come back out of the /events
endpoint in the shape the session viewer can parse.
"""

import io
import json
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


async def _share(pool, ws, object_type, object_id, user_id, owner_id, permission="read"):
    await pool.execute(
        "INSERT INTO shares (workspace_id, object_type, object_id, principal_type, "
        "principal_id, permission, created_by) VALUES ($1, $2, $3, 'user', $4, $5, $6)",
        UUID(ws),
        object_type,
        object_id,
        UUID(user_id),
        permission,
        UUID(owner_id),
    )


async def _workspace(client, key):
    r = await client.post(
        "/api/v1/workspaces",
        json={"name": "ws-" + unique_name()},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.asyncio
async def test_upload_inserts_events_and_events_roundtrip(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    up = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-1", "agent_name": "claude"},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    payload = up.json()
    assert payload["imported"] == 2
    assert payload["skipped"] is False

    meta = await client.get(
        f"/api/v1/workspaces/{ws}/transcripts/sess-1",
        headers=headers,
    )
    assert meta.status_code == 200
    assert meta.json()["event_count"] == 2

    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/transcripts/sess-1/events",
        headers=headers,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    assert [event["role"] for event in events] == ["user", "assistant"]
    assert events[0]["content"] == "hi"
    assert events[1]["content"] == "hello"


@pytest.mark.asyncio
async def test_reupload_is_noop_when_events_exist(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    first = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-dup", "agent_name": "claude"},
        headers=headers,
    )
    assert first.status_code == 201
    assert first.json()["imported"] == 2

    second = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
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
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "empty-shell", "agent_name": "claude"},
        headers=headers,
    )
    assert created.status_code == 201

    overview = await client.get(f"/api/v1/workspaces/{ws}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["sessions"] == []

    sidebar = await client.get(f"/api/v1/workspaces/{ws}/sidebar", headers=headers)
    assert sidebar.status_code == 200
    assert sidebar.json()["sessions"] == []

    my_sessions = await client.get(
        "/api/v1/me/sessions",
        params={"workspace_id": ws},
        headers=headers,
    )
    assert my_sessions.status_code == 200
    assert my_sessions.json()["sessions"] == []

    detail = await client.get(
        f"/api/v1/workspaces/{ws}/sessions/empty-shell",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["session_id"] == "empty-shell"


@pytest.mark.asyncio
async def test_event_created_session_lands_in_default_folder(client: AsyncClient):
    """An un-targeted push hook (e.g. Codex, which has no session-start hook so
    the first event creates the row) must land in the Default folder, never at
    the workspace root with no folder."""
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    pushed = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events",
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
        "/api/v1/me/sessions", params={"workspace_id": ws}, headers=headers
    )
    assert listed.status_code == 200
    session = next(
        s for s in listed.json()["sessions"] if s["session_id"] == "codex-untargeted"
    )
    assert session["session_folder_id"] is not None
    assert session["session_folder_name"] == "Default"


@pytest.mark.asyncio
async def test_transcript_upload_targets_explicit_session_folder(client: AsyncClient):
    """A pinned repo passes session_folder_id with the transcript upload, so a
    session whose row is first created by the upload lands in that folder."""
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    folder = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders", json={"name": "Pinned"}, headers=headers
    )
    assert folder.status_code in (200, 201)
    folder_id = folder.json()["id"]

    upload = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("t.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={
            "session_id": "pinned-session",
            "agent_name": "claude",
            "session_folder_id": folder_id,
        },
        headers=headers,
    )
    assert upload.status_code == 201

    listed = await client.get(
        "/api/v1/me/sessions", params={"workspace_id": ws}, headers=headers
    )
    session = next(
        s for s in listed.json()["sessions"] if s["session_id"] == "pinned-session"
    )
    assert session["session_folder_id"] == folder_id
    assert session["session_folder_name"] == "Pinned"


@pytest.mark.asyncio
async def test_event_stream_pin_targets_folder(client: AsyncClient):
    """A pinned repo streams session_folder_id on every event. An agent with no
    session-start hook (Codex) creates the row from its first event, which must
    land in the pinned folder, not Default."""
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    folder = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders", json={"name": "Repo"}, headers=headers
    )
    folder_id = folder.json()["id"]

    pushed = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events",
        json={
            "agent_name": "codex",
            "event_type": "assistant_message",
            "content": "pinned codex session",
            "session_id": "codex-pinned",
            "session_folder_id": folder_id,
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    listed = await client.get(
        "/api/v1/me/sessions", params={"workspace_id": ws}, headers=headers
    )
    session = next(s for s in listed.json()["sessions"] if s["session_id"] == "codex-pinned")
    assert session["session_folder_id"] == folder_id


@pytest.mark.asyncio
async def test_streamed_pin_does_not_re_home_explicit_move_to_root(client: AsyncClient):
    """The folder is set once at row creation. A later streamed pin must not undo
    an explicit move-to-root, or the agent would fight a user's manual move."""
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    folder = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders", json={"name": "Repo"}, headers=headers
    )
    folder_id = folder.json()["id"]

    async def push():
        return await client.post(
            f"/api/v1/workspaces/{ws}/sessions/events",
            json={
                "agent_name": "codex",
                "event_type": "assistant_message",
                "content": "turn",
                "session_id": "moved-session",
                "session_folder_id": folder_id,
            },
            headers=headers,
        )

    await push()
    listed = await client.get(
        "/api/v1/me/sessions", params={"workspace_id": ws}, headers=headers
    )
    row_id = next(
        s["id"] for s in listed.json()["sessions"] if s["session_id"] == "moved-session"
    )

    moved = await client.post(
        f"/api/v1/workspaces/{ws}/session-folders/assign",
        json={"session_row_ids": [row_id], "folder_id": None},
        headers=headers,
    )
    assert moved.status_code == 200

    await push()  # another turn keeps streaming the pin
    after = await client.get(
        "/api/v1/me/sessions", params={"workspace_id": ws}, headers=headers
    )
    session = next(s for s in after.json()["sessions"] if s["session_id"] == "moved-session")
    assert session["session_folder_id"] is None


@pytest.mark.asyncio
async def test_replace_reimports_existing_session(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
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
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-replace", "agent_name": "claude"},
        headers=headers,
    )
    assert first.status_code == 201
    assert first.json()["imported"] == 2

    second = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(replacement), "application/jsonl")},
        data={"session_id": "sess-replace", "agent_name": "claude", "replace": "true"},
        headers=headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["skipped"] is False
    assert second.json()["imported"] == 1

    events_resp = await client.get(
        f"/api/v1/workspaces/{ws}/transcripts/sess-replace/events",
        headers=headers,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    assert [event["content"] for event in events] == ["updated"]


@pytest.mark.asyncio
async def test_workspace_sidebar_sessions_include_human_author(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    author = me.json()["display_name"]

    pushed = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events/batch",
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

    overview = await client.get(f"/api/v1/workspaces/{ws}/overview", headers=headers)
    assert overview.status_code == 200
    [overview_session] = overview.json()["sessions"]
    assert overview_session["user_name"] == author
    assert overview_session["agent_name"] == "claude"

    sidebar = await client.get(f"/api/v1/workspaces/{ws}/sidebar", headers=headers)
    assert sidebar.status_code == 200
    [sidebar_session] = sidebar.json()["sessions"]
    assert sidebar_session["user_name"] == author
    assert sidebar_session["agent_name"] == "claude"
    etag = sidebar.headers["etag"]

    updated = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events/batch",
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
        f"/api/v1/workspaces/{ws}/sidebar",
        headers={**headers, "If-None-Match": etag},
    )
    assert refreshed.status_code == 200
    assert refreshed.headers["etag"] != etag


@pytest.mark.asyncio
async def test_session_linear_ticket_labels_are_extracted(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    linear_prompt = """You are working on a Linear ticket `FER-19`

Issue context:
Identifier: FER-19
Title: We should be able to update the top background color gradient/image on the homepage of a Stash
Current status: In Progress
URL: https://linear.app/ferganalabs/issue/FER-19/we-should-be-able-to-update-the-top-background-color-gradientimage-on
"""

    pushed = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "codex",
                    "event_type": "user_message",
                    "content": linear_prompt,
                    "session_id": "sess-linear",
                }
            ]
        },
        headers=headers,
    )
    assert pushed.status_code == 201

    overview = await client.get(f"/api/v1/workspaces/{ws}/overview", headers=headers)
    assert overview.status_code == 200
    [overview_session] = overview.json()["sessions"]
    assert overview_session["linear_tickets"] == [
        {
            "ticket_identifier": "FER-19",
            "ticket_title": (
                "We should be able to update the top background color gradient/image "
                "on the homepage of a Stash"
            ),
            "ticket_url": (
                "https://linear.app/ferganalabs/issue/FER-19/"
                "we-should-be-able-to-update-the-top-background-color-gradientimage-on"
            ),
            "source": "linear_preamble",
            "confidence": 1.0,
            "linear_issue_id": None,
            "ticket_status": None,
            "ticket_assignee_name": None,
            "ticket_team_key": None,
            "ticket_team_name": None,
            "ticket_project_name": None,
            "linear_updated_at": None,
            "enriched_at": None,
        }
    ]

    detail = await client.get(
        f"/api/v1/workspaces/{ws}/sessions/sess-linear",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["linear_tickets"][0]["ticket_identifier"] == "FER-19"

    mine = await client.get(
        f"/api/v1/me/sessions?workspace_id={ws}",
        headers=headers,
    )
    assert mine.status_code == 200
    assert mine.json()["sessions"][0]["linear_tickets"][0]["ticket_identifier"] == "FER-19"


@pytest.mark.asyncio
async def test_workspace_sidebar_etag_changes_after_generated_title(
    client: AsyncClient,
    pool,
):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    pushed = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events/batch",
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

    sidebar = await client.get(f"/api/v1/workspaces/{ws}/sidebar", headers=headers)
    assert sidebar.status_code == 200
    etag = sidebar.headers["etag"]
    [fallback_session] = sidebar.json()["sessions"]
    assert fallback_session["title"] == "Make the release checklist easier to scan"

    await pool.execute(
        """
        INSERT INTO session_titles (workspace_id, session_id, title, source_hash)
        VALUES ($1, $2, $3, $4)
        """,
        UUID(ws),
        "sess-generated-title",
        "Release Checklist Readability",
        "test-source-hash",
    )

    refreshed = await client.get(
        f"/api/v1/workspaces/{ws}/sidebar",
        headers={**headers, "If-None-Match": etag},
    )
    assert refreshed.status_code == 200
    assert refreshed.headers["etag"] != etag
    [generated_session] = refreshed.json()["sessions"]
    assert generated_session["title"] == "Release Checklist Readability"


@pytest.mark.asyncio
async def test_session_detail_returns_files_touched_and_artifacts_list(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={
            "session_id": "sess-files",
            "agent_name": "codex",
            "files_touched": ["frontend/src/app/page.tsx", "backend/main.py"],
        },
        headers=headers,
    )
    assert created.status_code == 201

    detail = await client.get(
        f"/api/v1/workspaces/{ws}/sessions/sess-files",
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
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
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
        f"/api/v1/workspaces/{ws}/sessions/{session_row_id}",
        headers=headers,
    )
    assert trashed.status_code == 204

    purged = await client.delete(
        f"/api/v1/workspaces/{ws}/sessions/{session_row_id}/purge",
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
    ws = await _workspace(client, key)
    workspace_id = UUID(ws)
    user_uuid = UUID(user_id)
    headers = {"Authorization": f"Bearer {key}"}

    created = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "sess-shared-artifacts", "agent_name": "codex"},
        headers=headers,
    )
    assert created.status_code == 201
    session_row_id = UUID(created.json()["id"])

    other_created = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "sess-other-artifacts", "agent_name": "codex"},
        headers=headers,
    )
    assert other_created.status_code == 201
    other_session_row_id = UUID(other_created.json()["id"])

    await pool.execute(
        "INSERT INTO files "
        "(workspace_id, name, content_type, size_bytes, storage_key, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        workspace_id,
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
        f"/api/v1/workspaces/{ws}/sessions/{session_row_id}",
        headers=headers,
    )
    assert trashed.status_code == 204

    purged = await client.delete(
        f"/api/v1/workspaces/{ws}/sessions/{session_row_id}/purge",
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
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    pushed = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events/batch",
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
        f"/api/v1/workspaces/{ws}/transcripts/sess-streamed/events",
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
    ws = await _workspace(client, key)
    big = b"x" * (50 * 1024 * 1024 + 1)
    r = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(big), "application/jsonl")},
        data={"session_id": "sess-big", "agent_name": "claude"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_non_member_forbidden(client: AsyncClient):
    owner = await _register(client)
    other = await _register(client)
    ws = await _workspace(client, owner)
    r = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess", "agent_name": "claude"},
        headers={"Authorization": f"Bearer {other}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_write_session_ingress(client: AsyncClient, pool):
    owner_key, owner_id = await _register_user(client)
    viewer_key, viewer_id = await _register_user(client)
    ws = await _workspace(client, owner_key)
    owner_headers = {"Authorization": f"Bearer {owner_key}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_key}"}

    folder = await client.post(
        f"/api/v1/workspaces/{ws}/folders",
        json={"name": "Shared"},
        headers=owner_headers,
    )
    assert folder.status_code == 201
    await _share(pool, ws, "folder", UUID(folder.json()["id"]), viewer_id, owner_id)

    event_resp = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events",
        json={
            "agent_name": "codex",
            "event_type": "assistant_message",
            "content": "viewer should not write",
            "session_id": "viewer-event",
        },
        headers=viewer_headers,
    )
    assert event_resp.status_code == 403

    batch_resp = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "codex",
                    "event_type": "assistant_message",
                    "content": "viewer should not batch write",
                    "session_id": "viewer-batch",
                }
            ]
        },
        headers=viewer_headers,
    )
    assert batch_resp.status_code == 403

    transcript_resp = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "viewer-transcript", "agent_name": "codex"},
        headers=viewer_headers,
    )
    assert transcript_resp.status_code == 403

    session_resp = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "viewer-shell", "agent_name": "codex"},
        headers=viewer_headers,
    )
    assert session_resp.status_code == 403

    assert (
        await pool.fetchval("SELECT COUNT(*) FROM history_events WHERE workspace_id = $1", ws) == 0
    )
    assert await pool.fetchval("SELECT COUNT(*) FROM sessions WHERE workspace_id = $1", ws) == 0


@pytest.mark.asyncio
async def test_viewer_cannot_mutate_existing_session_artifacts_or_materialized_pages(
    client: AsyncClient,
    pool,
):
    owner_key, owner_id = await _register_user(client)
    viewer_key, viewer_id = await _register_user(client)
    ws = await _workspace(client, owner_key)
    owner_headers = {"Authorization": f"Bearer {owner_key}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_key}"}

    created = await client.post(
        f"/api/v1/workspaces/{ws}/sessions",
        json={"session_id": "owner-session", "agent_name": "codex"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    session_row_id = created.json()["id"]
    await _share(pool, ws, "session", UUID(session_row_id), viewer_id, owner_id)

    pushed = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/events",
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
        f"/api/v1/workspaces/{ws}/sessions/{session_row_id}/artifacts",
        files={"file": ("artifact.txt", io.BytesIO(b"secret"), "text/plain")},
        data={"file_path": "artifact.txt"},
        headers=viewer_headers,
    )
    assert artifact_resp.status_code == 404

    folder_resp = await client.post(
        f"/api/v1/workspaces/{ws}/folders",
        json={"name": "Materialized"},
        headers=owner_headers,
    )
    assert folder_resp.status_code == 201
    materialize_resp = await client.post(
        f"/api/v1/workspaces/{ws}/sessions/owner-session/materialize",
        json={"folder_id": folder_resp.json()["id"]},
        headers=viewer_headers,
    )
    assert materialize_resp.status_code == 403

    assert (
        await pool.fetchval(
            "SELECT COUNT(*) FROM session_artifacts WHERE session_id = $1",
            UUID(session_row_id),
        )
        == 0
    )
    assert await pool.fetchval("SELECT COUNT(*) FROM pages WHERE workspace_id = $1", ws) == 0
