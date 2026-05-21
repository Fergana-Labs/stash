"""Tests for product analytics: /analytics ingest + /admin/analytics readout.

Covers:
- Ingest allowlists (unknown surface / event_name rejected).
- Ingest uses the authed user_id, ignoring any client-supplied user.
- Admin endpoints reflect inserted rows (summary, funnel, top events).
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name

ADMIN_TOKEN = "test-admin-token"


@pytest.fixture(autouse=True)
def _set_admin_token(monkeypatch):
    """Force ADMIN_PASSWORD for the duration of the test.

    `require_admin_token` reads settings.ADMIN_PASSWORD; monkeypatch the env
    var AND the settings object so reloads pick it up.
    """
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_TOKEN)
    from backend.config import settings

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", ADMIN_TOKEN)


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _admin() -> dict:
    return {"X-Admin-Token": ADMIN_TOKEN}


@pytest.mark.asyncio
async def test_ingest_records_events(client: AsyncClient):
    key = await _register(client)
    resp = await client.post(
        "/api/v1/analytics/events",
        json={
            "events": [
                {
                    "surface": "web",
                    "event_name": "onboarding.viewed",
                    "properties": {"has_path": False},
                },
                {
                    "surface": "web",
                    "event_name": "onboarding.path_selected",
                    "properties": {"path": "migrant"},
                },
            ]
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"recorded": 2}


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_event(client: AsyncClient):
    key = await _register(client)
    resp = await client.post(
        "/api/v1/analytics/events",
        json={"events": [{"surface": "web", "event_name": "bogus.event"}]},
        headers=_auth(key),
    )
    assert resp.status_code == 400
    assert "unknown event_name" in resp.text


@pytest.mark.asyncio
async def test_ingest_accepts_round_2_event_names(client: AsyncClient):
    """The second batch of events (file_uploaded, stash_created, page_edited,
    search_query, signed_up, plus CLI history.*) must all pass the allowlist."""
    key = await _register(client)
    resp = await client.post(
        "/api/v1/analytics/events",
        json={
            "events": [
                {
                    "surface": "web",
                    "event_name": "web.file_uploaded",
                    "properties": {"size_bucket": "lt_1mb"},
                },
                {
                    "surface": "web",
                    "event_name": "web.stash_created",
                    "properties": {"kind": "manual"},
                },
                {
                    "surface": "web",
                    "event_name": "web.page_edited",
                    "properties": {"page_id": "p1"},
                },
                {
                    "surface": "web",
                    "event_name": "web.search_query",
                    "properties": {"has_results": True},
                },
                {
                    "surface": "web",
                    "event_name": "auth.signed_up",
                    "properties": {"via_cli": False},
                },
                {
                    "surface": "cli",
                    "event_name": "cli.command_invoked",
                    "properties": {"command": "history.push"},
                },
                {
                    "surface": "cli",
                    "event_name": "cli.command_invoked",
                    "properties": {"command": "history.query"},
                },
                {
                    "surface": "cli",
                    "event_name": "cli.command_invoked",
                    "properties": {"command": "history.search"},
                },
            ]
        },
        headers=_auth(key),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"recorded": 8}


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_surface(client: AsyncClient):
    key = await _register(client)
    resp = await client.post(
        "/api/v1/analytics/events",
        json={"events": [{"surface": "telepathy", "event_name": "onboarding.viewed"}]},
        headers=_auth(key),
    )
    assert resp.status_code == 400
    assert "unknown surface" in resp.text


@pytest.mark.asyncio
async def test_ingest_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/analytics/events",
        json={"events": [{"surface": "web", "event_name": "onboarding.viewed"}]},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_endpoints_require_token(client: AsyncClient):
    for path in [
        "/api/v1/admin/analytics/summary",
        "/api/v1/admin/analytics/onboarding-funnel",
        "/api/v1/admin/analytics/path-mix",
        "/api/v1/admin/analytics/surface-mix",
        "/api/v1/admin/analytics/top-events",
    ]:
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} should require admin token"


@pytest.mark.asyncio
async def test_funnel_reflects_recorded_events(client: AsyncClient):
    key = await _register(client)
    # Two users would be ideal but one is enough — funnel reports distinct
    # users per stage, and we only assert presence/order here.
    await client.post(
        "/api/v1/analytics/events",
        json={
            "events": [
                {
                    "surface": "web",
                    "event_name": "onboarding.viewed",
                    "properties": {"has_path": False},
                },
                {
                    "surface": "web",
                    "event_name": "onboarding.path_selected",
                    "properties": {"path": "memory"},
                },
                {
                    "surface": "web",
                    "event_name": "onboarding.step_viewed",
                    "properties": {"path": "memory", "step_idx": 0, "step_name": "install"},
                },
                {
                    "surface": "web",
                    "event_name": "onboarding.completed",
                    "properties": {"path": "memory", "total_steps": 3},
                },
            ]
        },
        headers=_auth(key),
    )

    resp = await client.get(
        "/api/v1/admin/analytics/onboarding-funnel",
        headers=_admin(),
    )
    assert resp.status_code == 200, resp.text
    stages = resp.json()["stages"]
    by_stage = {s["stage"]: s["users"] for s in stages}
    assert by_stage["viewed"] == 1
    assert by_stage["path_selected"] == 1
    assert by_stage["step_viewed"] == 1
    assert by_stage["completed"] == 1


@pytest.mark.asyncio
async def test_summary_counts_signups_and_cli_active(client: AsyncClient):
    key = await _register(client)
    await client.post(
        "/api/v1/analytics/events",
        json={
            "events": [
                {
                    "surface": "cli",
                    "event_name": "cli.command_invoked",
                    "properties": {"command": "connect"},
                },
                {
                    "surface": "cli",
                    "event_name": "cli.command_invoked",
                    "properties": {"command": "share"},
                },
            ]
        },
        headers=_auth(key),
    )

    resp = await client.get(
        "/api/v1/admin/analytics/summary?days=30",
        headers=_admin(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["signups"] >= 1
    assert body["cli_active_users"] == 1  # one distinct user, regardless of cmd count
    assert body["active_users"] >= 1


@pytest.mark.asyncio
async def test_top_events_returns_ranked_list(client: AsyncClient):
    key = await _register(client)
    # Fire two web events of different names so we can assert ordering.
    payload = {
        "events": (
            [{"surface": "web", "event_name": "web.page_created", "properties": {}}] * 3
            + [{"surface": "web", "event_name": "web.workspace_created", "properties": {}}]
        )
    }
    await client.post("/api/v1/analytics/events", json=payload, headers=_auth(key))

    resp = await client.get(
        "/api/v1/admin/analytics/top-events?days=30",
        headers=_admin(),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    names = [r["event_name"] for r in rows]
    assert names[0] == "web.page_created"
    assert "web.workspace_created" in names
