"""The curator log endpoint: what each nightly curation learned.

One entry per run, newest first — the run's stored final message is the
learning; a failed run carries its error instead of a summary.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import agent_service
from backend.services.sprite_agent_service import RUN_FAILED_PREFIX

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("clog"), "password": "securepassword1"},
    )
    return r.json()["api_key"], UUID(r.json()["id"])


def _auth(k: str) -> dict:
    return {"Authorization": f"Bearer {k}"}


async def _seed_run(pool, uid: UUID, curator_id: str, stamp: str, at: datetime, final: str):
    session = f"agent-curate-{curator_id}-{stamp}"
    await pool.execute(
        "INSERT INTO history_events (owner_user_id, created_by, agent_name, event_type, "
        "content, session_id, created_at) VALUES "
        "($1, $1, 'Memory curator', 'user_message', '(prompt)', $2, $3), "
        "($1, $1, 'Memory curator', 'assistant_message', $4, $2, $5)",
        uid,
        session,
        at,
        final,
        at + timedelta(minutes=3),
    )
    return session


async def _seed_started_run(pool, uid: UUID, curator_id: str, stamp: str, at: datetime) -> str:
    """A run that has begun but written no final message yet."""
    session = f"agent-curate-{curator_id}-{stamp}"
    await pool.execute(
        "INSERT INTO history_events (owner_user_id, created_by, agent_name, event_type, "
        "content, session_id, created_at) VALUES "
        "($1, $1, 'Memory curator', 'user_message', '(prompt)', $2, $3)",
        uid,
        session,
        at,
    )
    return session


@pytest.mark.asyncio
async def test_log_lists_runs_newest_first(client: AsyncClient, pool):
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await _seed_run(
        pool, uid, curator["id"], "n1", datetime(2026, 8, 7, 9, 0, tzinfo=UTC), "First night."
    )
    await _seed_run(
        pool, uid, curator["id"], "n2", datetime(2026, 8, 8, 9, 0, tzinfo=UTC), "Second night."
    )

    r = await client.get("/api/v1/me/curator-log", headers=_auth(key))
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert [e["summary"] for e in entries] == ["Second night.", "First night."]
    assert entries[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_failed_runs_carry_their_error_not_a_summary(client: AsyncClient, pool):
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    await _seed_run(
        pool,
        uid,
        curator["id"],
        "n1",
        datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
        f"{RUN_FAILED_PREFIX} credential expired",
    )
    entries = (await client.get("/api/v1/me/curator-log", headers=_auth(key))).json()["entries"]
    assert entries[0]["status"] == "failed"
    assert entries[0]["summary"] is None
    assert entries[0]["error"] == "credential expired"


@pytest.mark.asyncio
async def test_a_pass_still_in_flight_reads_as_running_not_interrupted(
    client: AsyncClient, pool, sprite_exec
):
    """No final message means either "still writing" or "died mid-pass", and the
    turn lock is the only thing that tells them apart. Calling a live run
    interrupted tells the user tonight's curation failed while it is running."""
    key, uid = await _register(client)
    curator = await agent_service.get_or_create_curator(uid)
    session = await _seed_started_run(
        pool, uid, curator["id"], "n1", datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
    )

    await sprite_exec.redis.set(f"agent-turn:{session}", "1")
    entries = (await client.get("/api/v1/me/curator-log", headers=_auth(key))).json()["entries"]
    assert entries[0]["status"] == "running"
    assert entries[0]["summary"] is None

    await sprite_exec.redis.delete(f"agent-turn:{session}")
    entries = (await client.get("/api/v1/me/curator-log", headers=_auth(key))).json()["entries"]
    assert entries[0]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_empty_log_for_a_fresh_account(client: AsyncClient):
    key, _ = await _register(client)
    r = await client.get("/api/v1/me/curator-log", headers=_auth(key))
    assert r.status_code == 200
    assert r.json()["entries"] == []
