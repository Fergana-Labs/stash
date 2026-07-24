"""Named agents: CRUD, defaults, channel binding, scheduling, resolver override."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from backend.services import agent_service
from backend.tasks.agent_schedules import _is_due

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("agents"), "password": "securepassword1"},
    )
    return r.json()["api_key"]


def _auth(k: str) -> dict:
    return {"Authorization": f"Bearer {k}"}


@pytest.mark.asyncio
async def test_default_agent_autocreated_and_listed(client: AsyncClient):
    """A fresh account has exactly its two reserved agents: the default chat
    agent and the signup-provisioned Memory curator."""
    key = await _register(client)
    r = await client.get("/api/v1/me/agents", headers=_auth(key))
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert len(agents) == 2
    assert agents[0]["is_default"] is True  # default sorts first
    assert any(a["is_curator"] for a in agents)


@pytest.mark.asyncio
async def test_create_update_delete_agent(client: AsyncClient):
    key = await _register(client)
    await client.get("/api/v1/me/agents", headers=_auth(key))  # seed default

    created = (
        await client.post(
            "/api/v1/me/agents",
            json={
                "name": "Researcher",
                "model_provider": "openrouter",
                "system_prompt": "Be terse.",
            },
            headers=_auth(key),
        )
    ).json()
    assert created["name"] == "Researcher" and created["model_provider"] == "openrouter"

    updated = (
        await client.patch(
            f"/api/v1/me/agents/{created['id']}",
            json={"name": "Researcher 2", "model_provider": "anthropic"},
            headers=_auth(key),
        )
    ).json()
    assert updated["name"] == "Researcher 2" and updated["model_provider"] == "anthropic"

    r = await client.delete(f"/api/v1/me/agents/{created['id']}", headers=_auth(key))
    assert r.status_code == 200
    remaining = (await client.get("/api/v1/me/agents", headers=_auth(key))).json()["agents"]
    assert all(a["id"] != created["id"] for a in remaining)


@pytest.mark.asyncio
async def test_cannot_delete_default(client: AsyncClient):
    key = await _register(client)
    default = (await client.get("/api/v1/me/agents", headers=_auth(key))).json()["agents"][0]
    r = await client.delete(f"/api/v1/me/agents/{default['id']}", headers=_auth(key))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_invalid_model_provider_and_schedule(client: AsyncClient):
    key = await _register(client)
    bad = await client.post(
        "/api/v1/me/agents", json={"name": "x", "model_provider": "bogus"}, headers=_auth(key)
    )
    assert bad.status_code == 400
    no_cron = await client.post(
        "/api/v1/me/agents", json={"name": "x", "run_mode": "scheduled"}, headers=_auth(key)
    )
    assert no_cron.status_code == 400


@pytest.mark.asyncio
async def test_channel_binding_is_unique_and_resolves(client: AsyncClient, _db_pool):
    key = await _register(client)
    agents = (await client.get("/api/v1/me/agents", headers=_auth(key))).json()["agents"]
    default_id = agents[0]["id"]
    a = (
        await client.post("/api/v1/me/agents", json={"name": "Slackbot"}, headers=_auth(key))
    ).json()
    b = (await client.post("/api/v1/me/agents", json={"name": "Other"}, headers=_auth(key))).json()

    await client.patch(
        f"/api/v1/me/agents/{a['id']}",
        json={"name": "Slackbot", "slack_bound": True},
        headers=_auth(key),
    )
    # Binding a second agent clears the first (unique per user).
    await client.patch(
        f"/api/v1/me/agents/{b['id']}",
        json={"name": "Other", "slack_bound": True},
        headers=_auth(key),
    )
    listed = (await client.get("/api/v1/me/agents", headers=_auth(key))).json()["agents"]
    bound = [x for x in listed if x["slack_bound"]]
    assert len(bound) == 1 and bound[0]["id"] == b["id"]

    user_id = (await client.get("/api/v1/users/me", headers=_auth(key))).json()["id"]
    from uuid import UUID

    resolved = await agent_service.channel_agent(UUID(user_id), "slack")
    assert resolved["id"] == b["id"]
    # Telegram is unbound → falls back to the default agent.
    tg = await agent_service.channel_agent(UUID(user_id), "telegram")
    assert tg["id"] == default_id


def test_cron_due_check():
    now = datetime(2026, 7, 6, 9, 0, tzinfo=UTC)
    # A daily 9am job whose last run was yesterday is due.
    assert _is_due("0 9 * * *", now - timedelta(days=1), now) is True
    # Last run 08:59; the 09:00 tick hasn't run yet → due now.
    assert _is_due("0 9 * * *", now - timedelta(minutes=1), now) is True
    # Just ran at 09:00; next tick is tomorrow → not due (no double-fire).
    assert _is_due("0 9 * * *", now, now) is False
    # Bad cron → never due, no crash.
    assert _is_due("not a cron", None, now) is False


@pytest.mark.asyncio
async def test_scheduled_agent_seeds_baseline_and_becomes_due(client: AsyncClient, _db_pool):
    """A freshly-scheduled agent must fire on its next tick — regression for the
    bug where last_run_at stayed NULL forever and it never ran."""
    from uuid import UUID

    from backend.services import agent_service

    key = await _register(client)
    a = (
        await client.post(
            "/api/v1/me/agents",
            json={
                "name": "Daily",
                "run_mode": "scheduled",
                "schedule_cron": "* * * * *",
                "schedule_prompt": "go",
            },
            headers=_auth(key),
        )
    ).json()
    # Baseline seeded on create (not NULL) so the cron can become due.
    row = await _db_pool.fetchrow("SELECT last_run_at FROM agents WHERE id = $1", UUID(a["id"]))
    assert row["last_run_at"] is not None

    # Rewind the baseline; the every-minute cron is now due.
    await _db_pool.execute(
        "UPDATE agents SET last_run_at = now() - interval '5 minutes' WHERE id = $1", UUID(a["id"])
    )
    due = await agent_service.list_scheduled()
    from backend.tasks.agent_schedules import _is_due

    target = next(x for x in due if x["id"] == a["id"])
    assert _is_due(target["schedule_cron"], target["last_run_at"], datetime.now(UTC)) is True


@pytest.mark.asyncio
async def test_switch_to_scheduled_seeds_baseline(client: AsyncClient, _db_pool):
    from uuid import UUID

    key = await _register(client)
    a = (await client.post("/api/v1/me/agents", json={"name": "C"}, headers=_auth(key))).json()
    assert a["run_mode"] == "chat"
    await client.patch(
        f"/api/v1/me/agents/{a['id']}",
        json={"run_mode": "scheduled", "schedule_cron": "* * * * *", "schedule_prompt": "go"},
        headers=_auth(key),
    )
    row = await _db_pool.fetchrow("SELECT last_run_at FROM agents WHERE id = $1", UUID(a["id"]))
    assert row["last_run_at"] is not None


@pytest.mark.asyncio
async def test_partial_patch_preserves_other_fields(client: AsyncClient):
    """PATCH {name} must not reset model/schedule/bindings to defaults."""
    key = await _register(client)
    a = (
        await client.post(
            "/api/v1/me/agents",
            json={"name": "Keep", "model_provider": "openrouter", "system_prompt": "Terse."},
            headers=_auth(key),
        )
    ).json()
    updated = (
        await client.patch(
            f"/api/v1/me/agents/{a['id']}", json={"name": "Renamed"}, headers=_auth(key)
        )
    ).json()
    assert updated["name"] == "Renamed"
    assert updated["model_provider"] == "openrouter"  # not clobbered to null
    assert updated["system_prompt"] == "Terse."


async def _push_event(
    client: AsyncClient, key: str, session_id: str, event_type: str, content: str
):
    r = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "Nightly",
            "event_type": event_type,
            "content": content,
            "session_id": session_id,
        },
        headers=_auth(key),
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_agent_runs_groups_sessions_oldest_first_with_failure_flag(client: AsyncClient):
    """The runs feed is the scheduled agent's whole history: one entry per
    per-run session in chronological order, flagged when the closing message
    is the stored run-failure marker."""
    key = await _register(client)
    a = (
        await client.post(
            "/api/v1/me/agents",
            json={
                "name": "Nightly",
                "run_mode": "scheduled",
                "schedule_cron": "0 8 * * *",
                "schedule_prompt": "Do the nightly thing.",
            },
            headers=_auth(key),
        )
    ).json()

    prefix = f"agent-sched-{a['id']}-"
    await _push_event(
        client, key, f"{prefix}20260722080000", "user_message", "Do the nightly thing."
    )
    await _push_event(client, key, f"{prefix}20260722080000", "assistant_message", "Done: 3 items.")
    await _push_event(
        client, key, f"{prefix}20260723080000", "user_message", "Do the nightly thing."
    )
    await _push_event(
        client, key, f"{prefix}20260723080000", "assistant_message", "⚠️ Agent run failed: boom"
    )

    r = await client.get(f"/api/v1/me/agents/{a['id']}/runs", headers=_auth(key))
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert [run["session_id"] for run in runs] == [
        f"{prefix}20260722080000",
        f"{prefix}20260723080000",
    ]
    assert [run["failed"] for run in runs] == [False, True]
    assert runs[0]["messages"] == [
        {"role": "user", "content": "Do the nightly thing."},
        {"role": "assistant", "content": "Done: 3 items."},
    ]

    # limit keeps the newest runs while preserving chronological order.
    limited = (
        await client.get(f"/api/v1/me/agents/{a['id']}/runs?limit=1", headers=_auth(key))
    ).json()["runs"]
    assert [run["session_id"] for run in limited] == [f"{prefix}20260723080000"]


@pytest.mark.asyncio
async def test_agent_runs_is_owner_scoped(client: AsyncClient):
    """Another user's agent id must 404, not leak run history."""
    key_a = await _register(client)
    key_b = await _register(client)
    a = (
        await client.post(
            "/api/v1/me/agents",
            json={
                "name": "Nightly",
                "run_mode": "scheduled",
                "schedule_cron": "0 8 * * *",
                "schedule_prompt": "Nightly.",
            },
            headers=_auth(key_a),
        )
    ).json()
    r = await client.get(f"/api/v1/me/agents/{a['id']}/runs", headers=_auth(key_b))
    assert r.status_code == 404
