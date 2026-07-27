"""Run history for a named agent: a paginated list of its past scheduled runs,
derived from each run's per-run session events plus the live turn lock.

These tests prove the user-facing reasons: a user can see when each run
happened, how long it took, whether it completed, failed (with the error),
was interrupted, or is still running — instead of only the single latest run
the agents table surfaces via last_run_at / last_run_error.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import sprite_agent_service
from backend.tasks.session_titles import generate_session_title

from .conftest import FakeRedis, unique_name

# Per-run session id prefix convention (must match
# sprite_agent_service.build_scheduled_turn).
_CURATE_PREFIX = "agent-curate-"
_SCHED_PREFIX = "agent-sched-"


@pytest.fixture
def run_history_redis(monkeypatch):
    """Isolate run-history tests from the real substrate.

    The /runs endpoint reads the per-session turn lock from Redis (the live
    source of truth for "is a turn running"), and the batch event push
    dispatches a Celery title-generation task when an Anthropic key is set.
    Both would reach a real broker in tests, so this fixture swaps in a
    FakeRedis for the lock check and no-ops the Celery dispatch — the tests
    exercise run-history derivation, not the broker. Yields the FakeRedis so
    a test can hold the lock to simulate a running turn.
    """
    fake_redis = FakeRedis()
    monkeypatch.setattr(sprite_agent_service, "_get_redis", lambda: fake_redis)
    monkeypatch.setattr(generate_session_title, "delay", lambda *a, **k: None)
    return fake_redis


async def _register(client: AsyncClient) -> tuple[str, UUID]:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("runs"), "password": "securepassword1"},
    )
    return r.json()["api_key"], UUID(r.json()["id"])


def _auth(k: str) -> dict:
    return {"Authorization": f"Bearer {k}"}


async def _push_events(client: AsyncClient, key: str, events: list[dict]) -> None:
    r = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={"events": events},
        headers=_auth(key),
    )
    assert r.status_code == 201


def _event(
    agent_name: str,
    event_type: str,
    content: str,
    session_id: str,
    created_at: datetime,
    tool_name: str | None = None,
) -> dict:
    e = {
        "agent_name": agent_name,
        "event_type": event_type,
        "content": content,
        "session_id": session_id,
        "created_at": created_at.isoformat(),
    }
    if tool_name is not None:
        e["tool_name"] = tool_name
    return e


@pytest.mark.asyncio
async def test_completed_failed_running_interrupted_in_one_list(
    client: AsyncClient, _db_pool, run_history_redis
):
    """A user opening an agent's run history sees four real outcomes side by
    side: a cleanly completed run, a run that died with an error, a run that
    is still mid-turn, and a run whose turn vanished without a terminal event
    (worker kill). Without this list the user could only see the *latest*
    run's status (last_run_error), losing every earlier run's outcome."""
    key, uid = await _register(client)
    agent = (
        await client.post(
            "/api/v1/me/agents",
            json={
                "name": "Daily report",
                "run_mode": "scheduled",
                "schedule_cron": "0 9 * * *",
                "schedule_prompt": "build the report",
            },
            headers=_auth(key),
        )
    ).json()
    agent_id = agent["id"]
    name = agent["name"]
    base = datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)

    completed_session = f"{_SCHED_PREFIX}{agent_id}-202607010900"
    failed_session = f"{_SCHED_PREFIX}{agent_id}-202607020900"
    interrupted_session = f"{_SCHED_PREFIX}{agent_id}-202607030900"
    running_session = f"{_SCHED_PREFIX}{agent_id}-202607040900"
    stopped_session = f"{_SCHED_PREFIX}{agent_id}-202607050900"

    await _push_events(
        client,
        key,
        [
            _event(name, "user_message", "build the report", completed_session, base),
            _event(
                name,
                "tool_use",
                "Bash: ls",
                completed_session,
                base + timedelta(seconds=30),
                tool_name="Bash",
            ),
            _event(
                name,
                "assistant_message",
                "Report v1 done",
                completed_session,
                base + timedelta(seconds=90),
            ),
            _event(
                name, "user_message", "build the report", failed_session, base + timedelta(days=1)
            ),
            _event(
                name,
                "assistant_message",
                "⚠️ Agent run failed: harness exited with code 2",
                failed_session,
                base + timedelta(days=1, seconds=5),
            ),
            _event(
                name,
                "user_message",
                "build the report",
                interrupted_session,
                base + timedelta(days=2),
            ),
            _event(
                name,
                "tool_use",
                "Bash: grep",
                interrupted_session,
                base + timedelta(days=2, seconds=10),
                tool_name="Bash",
            ),
            # running run: only its user_message exists so far; the turn lock
            # is held, so it must surface as running, not interrupted.
            _event(
                name,
                "user_message",
                "build the report",
                running_session,
                base + timedelta(days=3),
            ),
            # stopped run: the user stopped it mid-turn, so its terminal
            # assistant_message is the stop note — not a real answer. A user
            # scanning run history must distinguish "I stopped it" from "it
            # finished" and from "it died".
            _event(
                name,
                "user_message",
                "build the report",
                stopped_session,
                base + timedelta(days=4),
            ),
            _event(
                name,
                "assistant_message",
                "⏹ Stopped by user.",
                stopped_session,
                base + timedelta(days=4, seconds=20),
            ),
        ],
    )

    # Hold the turn lock for the running run — the API reads it from Redis.
    run_history_redis.data[f"agent-turn:{running_session}"] = b"lock-token"
    # Also hold the lock for the completed run, to prove a terminal event
    # out-ranks the lock: a run that just wrote its answer while the lock
    # released one tick late must read as completed, not running.
    run_history_redis.data[f"agent-turn:{completed_session}"] = b"stale-lock"

    r = await client.get(f"/api/v1/me/agents/{agent_id}/runs", headers=_auth(key))
    assert r.status_code == 200
    body = r.json()
    runs = {run["session_id"]: run for run in body["runs"]}
    assert len(runs) == 5

    completed = runs[completed_session]
    assert completed["status"] == "completed"  # terminal event out-ranks the stale lock
    assert completed["error"] is None
    assert completed["tool_count"] == 1
    assert completed["event_count"] == 3
    assert completed["duration_seconds"] == 90.0
    assert completed["finished_at"] is not None

    failed = runs[failed_session]
    assert failed["status"] == "failed"
    assert failed["error"] == "harness exited with code 2"
    assert failed["tool_count"] == 0

    interrupted = runs[interrupted_session]
    assert interrupted["status"] == "interrupted"
    assert interrupted["error"] is None
    assert interrupted["tool_count"] == 1
    # No terminal event recorded, so the run never finished — no finish
    # time and no duration, even though events exist after the prompt.
    assert interrupted["finished_at"] is None
    assert interrupted["duration_seconds"] is None

    running = runs[running_session]
    assert running["status"] == "running"
    assert running["error"] is None
    assert running["finished_at"] is None
    assert running["duration_seconds"] is None

    stopped = runs[stopped_session]
    assert stopped["status"] == "stopped"
    assert stopped["error"] is None
    assert stopped["duration_seconds"] == 20.0

    # Newest run first — the user scans top-down for the latest outcome.
    ordered = [run["session_id"] for run in body["runs"]]
    assert ordered == [
        stopped_session,
        running_session,
        interrupted_session,
        failed_session,
        completed_session,
    ]

    # app_url points at the existing session view, reuse, not a new surface.
    for run in body["runs"]:
        assert run["app_url"].endswith(f"/sessions/{run['session_id']}")


@pytest.mark.asyncio
async def test_curator_runs_are_listed(client: AsyncClient, _db_pool, run_history_redis):
    """The Memory curator is a scheduled agent too; its runs land under
    agent-curate- session ids, so the same list surfaces them — a user can
    audit nightly curator passes without a separate surface."""
    key, uid = await _register(client)
    from backend.services import agent_service

    curator = await agent_service.get_or_create_curator(uid)
    curator_id = curator["id"]
    name = curator["name"]
    base = datetime(2026, 7, 5, 8, 0, 0, tzinfo=UTC)
    session = f"{_CURATE_PREFIX}{curator_id}-202607050800"

    await _push_events(
        client,
        key,
        [
            _event(name, "user_message", "curate", session, base),
            _event(
                name,
                "assistant_message",
                "curated 12 pages",
                session,
                base + timedelta(seconds=120),
            ),
        ],
    )

    r = await client.get(f"/api/v1/me/agents/{curator_id}/runs", headers=_auth(key))
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["session_id"] == session
    assert runs[0]["status"] == "completed"
    assert runs[0]["agent_name"] == name


@pytest.mark.asyncio
async def test_pagination_and_has_more(client: AsyncClient, _db_pool, run_history_redis):
    """A long-running agent accumulates many runs; the list pages by
    started_at DESC and tells the UI when more runs exist, so an agent in
    its second month doesn't dump every run into one response."""
    key, uid = await _register(client)
    agent = (
        await client.post(
            "/api/v1/me/agents",
            json={
                "name": "Hourly",
                "run_mode": "scheduled",
                "schedule_cron": "0 * * * *",
                "schedule_prompt": "tick",
            },
            headers=_auth(key),
        )
    ).json()
    agent_id = agent["id"]
    name = agent["name"]
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)

    events = []
    for i in range(5):
        session = f"{_SCHED_PREFIX}{agent_id}-20260701{i:02d}00"
        ts = base + timedelta(hours=i)
        events.append(_event(name, "user_message", "tick", session, ts))
        events.append(
            _event(name, "assistant_message", f"ok {i}", session, ts + timedelta(seconds=10))
        )
    await _push_events(client, key, events)

    first = (
        await client.get(f"/api/v1/me/agents/{agent_id}/runs?limit=2&offset=0", headers=_auth(key))
    ).json()
    assert len(first["runs"]) == 2
    assert first["has_more"] is True
    assert first["runs"][0]["started_at"] > first["runs"][1]["started_at"]

    second = (
        await client.get(f"/api/v1/me/agents/{agent_id}/runs?limit=2&offset=2", headers=_auth(key))
    ).json()
    assert len(second["runs"]) == 2
    assert second["has_more"] is True

    last = (
        await client.get(f"/api/v1/me/agents/{agent_id}/runs?limit=2&offset=4", headers=_auth(key))
    ).json()
    assert len(last["runs"]) == 1
    assert last["has_more"] is False

    # No overlap between pages — pagination is a true partition of the runs.
    all_sessions = (
        [r["session_id"] for r in first["runs"]]
        + [r["session_id"] for r in second["runs"]]
        + [r["session_id"] for r in last["runs"]]
    )
    assert len(set(all_sessions)) == 5


@pytest.mark.asyncio
async def test_other_users_agent_is_404(client: AsyncClient, _db_pool, run_history_redis):
    """A run history is the agent owner's; another user must not read it
    (or even confirm the agent exists) by guessing its id. The response is
    the FastAPI error shape, never a runs list — so a leaked payload would
    fail the shape check even if the status slipped."""
    key_a, _ = await _register(client)
    key_b, _ = await _register(client)
    agent = (
        await client.post(
            "/api/v1/me/agents",
            json={
                "name": "private",
                "run_mode": "scheduled",
                "schedule_cron": "0 9 * * *",
                "schedule_prompt": "go",
            },
            headers=_auth(key_a),
        )
    ).json()
    # Seed real runs for A so a leak would have something to leak.
    name = agent["name"]
    sid = f"{_SCHED_PREFIX}{agent['id']}-202607010900"
    await _push_events(
        client,
        key_a,
        [
            _event(name, "user_message", "go", sid, datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC)),
            _event(
                name,
                "assistant_message",
                "done",
                sid,
                datetime(2026, 7, 1, 9, 0, 5, 0, tzinfo=UTC),
            ),
        ],
    )

    r = await client.get(f"/api/v1/me/agents/{agent['id']}/runs", headers=_auth(key_b))
    assert r.status_code == 404
    assert "runs" not in r.json()


@pytest.mark.asyncio
async def test_chat_agent_with_no_runs_returns_empty(
    client: AsyncClient, _db_pool, run_history_redis
):
    """A chat-mode agent's runs list is empty — its turns share one live
    session_id (agent-{uuid}), not a per-run scheduled session, so it must
    not be confused with scheduled runs. The user sees an empty list, not
    every chat turn."""
    key, uid = await _register(client)
    agents = (await client.get("/api/v1/me/agents", headers=_auth(key))).json()["agents"]
    default = next(a for a in agents if a["is_default"])
    # Push a chat turn under the chat session id convention.
    chat_session = f"agent-{uid.hex}-turn1"
    name = default["name"]
    await _push_events(
        client,
        key,
        [
            _event(name, "user_message", "hi", chat_session, datetime.now(UTC)),
            _event(name, "assistant_message", "hello", chat_session, datetime.now(UTC)),
        ],
    )

    r = await client.get(f"/api/v1/me/agents/{default['id']}/runs", headers=_auth(key))
    assert r.status_code == 200
    assert r.json() == {"runs": [], "has_more": False}
