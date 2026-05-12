"""Backend coverage for the rows-only transcript path.

Upload now parses JSONL into history_events rows; no R2 blob. The
roundtrip test confirms the events come back out of the /events
endpoint in the shape the chat viewer can parse.
"""

import io
import json
from uuid import UUID

import asyncpg
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


async def _register(client):
    r = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    assert r.status_code == 201
    return r.json()["api_key"]


async def _workspace(client, key):
    r = await client.post(
        "/api/v1/workspaces",
        json={"name": "ws-" + unique_name()},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.asyncio
async def test_upload_inserts_events_and_materializes_session(client: AsyncClient, pool):
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
    session_row = await pool.fetchrow(
        "SELECT id, session_id, agent_name FROM sessions WHERE workspace_id = $1 AND session_id = $2",
        UUID(ws),
        "sess-1",
    )
    assert session_row
    assert session_row["agent_name"] == "claude"

    spine = await client.get(f"/api/v1/stashes/{ws}/spine", headers=headers)
    assert spine.status_code == 200, spine.text
    assert [s["session_id"] for s in spine.json()["sessions"]] == ["sess-1"]

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
async def test_memory_event_materializes_session(client: AsyncClient, pool):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    event = await client.post(
        f"/api/v1/workspaces/{ws}/memory/events",
        json={
            "agent_name": "codex",
            "event_type": "user_message",
            "content": "start",
            "session_id": "sess-live",
            "metadata": {"cwd": "/repo"},
        },
        headers=headers,
    )
    assert event.status_code == 201, event.text

    session_row = await pool.fetchrow(
        "SELECT session_id, agent_name, cwd FROM sessions WHERE workspace_id = $1",
        UUID(ws),
    )
    assert session_row["session_id"] == "sess-live"
    assert session_row["agent_name"] == "codex"
    assert session_row["cwd"] == "/repo"

    spine = await client.get(f"/api/v1/stashes/{ws}/spine", headers=headers)
    assert spine.status_code == 200, spine.text
    assert spine.json()["sessions"][0]["session_id"] == "sess-live"


@pytest.mark.asyncio
async def test_database_rejects_event_only_workspace_session(client: AsyncClient, pool):
    key = await _register(client)
    ws = await _workspace(client, key)

    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await pool.execute(
            "INSERT INTO history_events (workspace_id, agent_name, event_type, content, session_id) "
            "VALUES ($1, 'codex', 'user_message', 'orphan', 'missing-session')",
            UUID(ws),
        )


@pytest.mark.asyncio
async def test_transcript_metadata_includes_summary_and_artifacts(client: AsyncClient, pool):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}

    up = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={"session_id": "sess-bundle", "agent_name": "claude"},
        headers=headers,
    )
    assert up.status_code == 201, up.text

    created = await client.post(
        f"/api/v1/workspaces/{ws}/stashes",
        json={"session_id": "sess-bundle", "agent_name": "claude"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    created_payload = created.json()
    stash_id = UUID(created_payload["id"])

    await pool.execute(
        "UPDATE sessions SET summary = $1, status = 'ready' WHERE id = $2",
        "Changed transcript sessions to include artifacts.",
        stash_id,
    )
    await pool.execute(
        "INSERT INTO session_artifacts (session_id, file_path, storage_key, size_bytes) "
        "VALUES ($1, 'backend/routers/transcripts.py', 'test-key', 123)",
        stash_id,
    )

    meta = await client.get(
        f"/api/v1/workspaces/{ws}/transcripts/sess-bundle",
        headers=headers,
    )
    assert meta.status_code == 200, meta.text
    payload = meta.json()
    assert payload["summary"] == "Changed transcript sessions to include artifacts."
    assert payload["status"] == "ready"
    assert payload["bundle_slug"] == created_payload["slug"]
    assert len(payload["artifacts"]) == 1
    assert payload["artifacts"][0]["file_path"] == "backend/routers/transcripts.py"
    assert payload["artifacts"][0]["size_bytes"] == 123

    spine = await client.get(f"/api/v1/stashes/{ws}/spine", headers=headers)
    assert spine.status_code == 200, spine.text
    session = spine.json()["sessions"][0]
    assert session["summary"] == "Changed transcript sessions to include artifacts."
    assert session["artifact_count"] == 1


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
