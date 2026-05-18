"""Backend coverage for the rows-only transcript path.

Upload now parses JSONL into history_events rows; no R2 blob. The
roundtrip test confirms the events come back out of the /events
endpoint in the shape the session viewer can parse.
"""

import io
import json

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


async def _stash(client, key, ws):
    r = await client.post(
        f"/api/v1/workspaces/{ws}/stashes",
        json={"title": "Default sessions", "items": []},
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
async def test_upload_adds_session_to_default_stash(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
    stash_id = await _stash(client, key, ws)
    headers = {"Authorization": f"Bearer {key}"}

    up = await client.post(
        f"/api/v1/workspaces/{ws}/transcripts",
        files={"file": ("s.jsonl", io.BytesIO(BODY), "application/jsonl")},
        data={
            "session_id": "sess-default",
            "agent_name": "claude",
            "default_stash_id": stash_id,
        },
        headers=headers,
    )
    assert up.status_code == 201, up.text

    stashes = await client.get(f"/api/v1/workspaces/{ws}/stashes", headers=headers)
    assert stashes.status_code == 200
    [stash] = [item for item in stashes.json()["stashes"] if item["id"] == stash_id]
    assert [item["object_type"] for item in stash["items"]] == ["session"]


@pytest.mark.asyncio
async def test_workspace_sidebar_sessions_include_human_author(client: AsyncClient):
    key = await _register(client)
    ws = await _workspace(client, key)
    headers = {"Authorization": f"Bearer {key}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    author = me.json()["display_name"] or me.json()["name"]

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
