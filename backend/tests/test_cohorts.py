"""Tests for /admin/cohorts/engagement.

The retention matrix is aggregated in SQL (one row per user × active period),
so these tests seed real rows in both event tables and assert the numbers the
dashboard renders: cohort sizes, retention, action counts, and the
events_filter=active exclusion of plugin firehose rows.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient

from .conftest import unique_name

ADMIN_TOKEN = "test-admin-token-with-32-plus-chars"


@pytest.fixture(autouse=True)
def _set_admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_TOKEN)
    from backend.config import settings

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", ADMIN_TOKEN)


async def _register_user(client: AsyncClient) -> UUID:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    api_key = resp.json()["api_key"]
    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {api_key}"})
    return UUID(me.json()["id"])


async def _insert_history_event(pool, user_id: UUID, created_at: datetime, metadata: str = "{}"):
    await pool.execute(
        "INSERT INTO history_events "
        "(owner_user_id, created_by, agent_name, event_type, content, metadata, "
        " created_at, session_id) "
        # $2 goes over the wire as text and is cast in SQL: the pool's jsonb
        # codec would otherwise re-encode the string into a double-encoded
        # JSON string, breaking ->> lookups.
        "VALUES ($1, $1, 'agent', 'message', 'hello', (($2)::text)::jsonb, $3, gen_random_uuid())",
        user_id,
        metadata,
        created_at,
    )


async def _insert_analytics_event(pool, user_id: UUID, created_at: datetime):
    await pool.execute(
        "INSERT INTO analytics_events (user_id, surface, event_name, created_at) "
        "VALUES ($1, 'web', 'onboarding.viewed', $2)",
        user_id,
        created_at,
    )


async def _fetch_cohorts(client: AsyncClient, **params) -> dict:
    resp = await client.get(
        "/api/v1/admin/cohorts/engagement",
        params=params,
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_monthly_retention_across_both_event_tables(client: AsyncClient, _db_pool):
    """User A is active in Jan and Feb, user B in Jan only: one January
    cohort with 100% period-0 and 50% period-1 retention. A's events live in
    history_events and B's in analytics_events, so the union feeds cohorts."""
    user_a = await _register_user(client)
    user_b = await _register_user(client)
    await _insert_history_event(_db_pool, user_a, datetime(2026, 1, 10, tzinfo=UTC))
    await _insert_history_event(_db_pool, user_a, datetime(2026, 2, 5, tzinfo=UTC))
    await _insert_analytics_event(_db_pool, user_b, datetime(2026, 1, 20, tzinfo=UTC))

    data = await _fetch_cohorts(client, bucket="month")

    assert data["bucket"] == "month"
    assert data["totals"] == {"users": 2, "events": 3}
    [cohort] = data["cohorts"]
    assert cohort["cohort_label"] == "2026-01"
    assert cohort["cohort_start"] == "2026-01-01T00:00:00+00:00"
    assert cohort["size"] == 2
    assert cohort["retention"][:3] == [1.0, 0.5, 0.0]
    assert cohort["active_users"][:3] == [2, 1, 0]
    assert cohort["actions"][:3] == [2, 1, 0]
    assert cohort["avg_cumulative_actions"][:3] == [1.0, 1.5, 1.5]


@pytest.mark.asyncio
async def test_future_mode_counts_later_activity(client: AsyncClient, _db_pool):
    """In future mode a user active in period 1 also counts as retained at
    period 1's predecessors — retention answers 'still around at or after p'."""
    user_a = await _register_user(client)
    user_b = await _register_user(client)
    await _insert_history_event(_db_pool, user_a, datetime(2026, 1, 10, tzinfo=UTC))
    await _insert_history_event(_db_pool, user_a, datetime(2026, 3, 5, tzinfo=UTC))
    await _insert_analytics_event(_db_pool, user_b, datetime(2026, 1, 20, tzinfo=UTC))

    data = await _fetch_cohorts(client, bucket="month", mode="future")

    [cohort] = data["cohorts"]
    # Standard mode would show period 1 as 0 (A skipped February); future
    # mode keeps A retained through period 2 because activity exists at p>=1.
    assert cohort["retention"][:3] == [1.0, 0.5, 0.5]


@pytest.mark.asyncio
async def test_active_filter_excludes_plugin_events(client: AsyncClient, _db_pool):
    """Plugin hook events (metadata.client set) are firehose, not engagement.
    With events_filter=active the user's cohort starts at their first real
    event, not the earlier plugin event."""
    user = await _register_user(client)
    await _insert_history_event(
        _db_pool, user, datetime(2026, 1, 10, tzinfo=UTC), metadata='{"client": "claude_code"}'
    )
    await _insert_analytics_event(_db_pool, user, datetime(2026, 2, 20, tzinfo=UTC))

    all_events = await _fetch_cohorts(client, bucket="month")
    active_only = await _fetch_cohorts(client, bucket="month", events_filter="active")

    assert all_events["cohorts"][0]["cohort_label"] == "2026-01"
    assert all_events["totals"] == {"users": 1, "events": 2}
    assert active_only["cohorts"][0]["cohort_label"] == "2026-02"
    assert active_only["totals"] == {"users": 1, "events": 1}


@pytest.mark.asyncio
async def test_week_bucket_floors_to_monday(client: AsyncClient, _db_pool):
    """Week cohorts anchor to the ISO Monday: a Wednesday first event lands
    in Monday's cohort, and the next week's event is period 1."""
    user = await _register_user(client)
    # 2026-03-04 is a Wednesday; its ISO week starts Monday 2026-03-02.
    await _insert_analytics_event(_db_pool, user, datetime(2026, 3, 4, tzinfo=UTC))
    await _insert_analytics_event(_db_pool, user, datetime(2026, 3, 9, tzinfo=UTC))

    data = await _fetch_cohorts(client, bucket="week")

    [cohort] = data["cohorts"]
    assert cohort["cohort_label"] == "2026-03-02"
    assert cohort["active_users"][:3] == [1, 1, 0]
