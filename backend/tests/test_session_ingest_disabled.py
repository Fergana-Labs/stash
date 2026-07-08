"""The SESSION_INGEST_DISABLED kill-switch.

When set, the plugin's five ingest endpoints must accept requests but persist
nothing, and session upsert must return a blank id/app_url so already-installed
plugins stop emitting the "Session: {url}" postscript and skip every upload.
The point of these tests: prove the switch stops storage AND blanks the two
fields the client keys the postscript off — the reason it works with no client
update at all.
"""

import io

import pytest

from backend.config import settings

from .conftest import unique_name


async def _register(client) -> str:
    r = await client.post(
        "/api/v1/users/register", json={"name": unique_name(), "password": "securepassword1"}
    )
    assert r.status_code == 201
    return r.json()["api_key"]


@pytest.fixture
def ingest_disabled(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_INGEST_DISABLED", True)


async def test_upsert_returns_blank_id_and_url_and_persists_nothing(client, pool, ingest_disabled):
    headers = {"Authorization": f"Bearer {await _register(client)}"}

    r = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "sess-off", "agent_name": "claude"},
        headers=headers,
    )
    assert r.status_code == 201
    body = r.json()
    # Blank id + app_url are what make the plugin drop the postscript and skip
    # the watcher / transcript upload — assert both, not just "no row".
    assert body["id"] == ""
    assert body["app_url"] == ""

    assert await pool.fetchval("SELECT COUNT(*) FROM sessions") == 0


async def test_events_are_dropped(client, pool, ingest_disabled):
    headers = {"Authorization": f"Bearer {await _register(client)}"}

    single = await client.post(
        "/api/v1/me/sessions/events",
        json={"agent_name": "claude", "event_type": "prompt", "content": "hi", "session_id": "s"},
        headers=headers,
    )
    assert single.status_code == 204

    batch = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {"agent_name": "claude", "event_type": "prompt", "content": "hi", "session_id": "s"}
            ]
        },
        headers=headers,
    )
    assert batch.status_code == 204

    assert await pool.fetchval("SELECT COUNT(*) FROM history_events") == 0


async def test_transcript_upload_is_dropped(client, pool, ingest_disabled):
    headers = {"Authorization": f"Bearer {await _register(client)}"}

    r = await client.post(
        "/api/v1/me/transcripts",
        data={"session_id": "sess-off", "agent_name": "claude"},
        files={"file": ("t.jsonl", io.BytesIO(b'{"type":"user","message":{"content":"hi"}}\n'))},
        headers=headers,
    )
    assert r.status_code == 204
    assert await pool.fetchval("SELECT COUNT(*) FROM history_events") == 0


async def test_switch_off_by_default_still_persists(client, pool):
    """Guard against the switch defaulting on: normal ingest must still store."""
    headers = {"Authorization": f"Bearer {await _register(client)}"}

    r = await client.post(
        "/api/v1/me/sessions",
        json={"session_id": "sess-on", "agent_name": "claude"},
        headers=headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"]
    assert body["app_url"].endswith("/sessions/sess-on")
    assert await pool.fetchval("SELECT COUNT(*) FROM sessions") == 1
