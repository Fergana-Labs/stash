"""A slow queue must not turn periodic syncs into duplicate work or silent staleness."""

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from backend.config import settings
from backend.services import alert_service, source_service, source_sync_service
from backend.tasks import sources

from .test_sources import _auth, _register


async def make_source(client):
    key, owner = await _register(client, "sync_claim")
    source = await source_service.create_source(
        owner_user_id=owner,
        source_type="google_drive_folder",
        external_ref="folder",
        display_name="Skills",
    )
    return key, UUID(source["id"])


@pytest.mark.asyncio
async def test_concurrent_triggers_publish_one_job_and_stale_deliveries_do_not_run(
    client, monkeypatch
):
    _, sid = await make_source(client)
    published = []
    monkeypatch.setattr(
        source_sync_service.celery, "send_task", lambda *a, **kw: published.append(kw)
    )
    claims = await asyncio.gather(*(source_sync_service.enqueue_sync(sid) for _ in range(8)))
    task_id = next(c for c in claims if c is not None)
    assert len(published) == 1
    assert await source_service.due_sources() == []
    run = AsyncMock(return_value={"status": "done"})
    monkeypatch.setattr(sources, "_sync_source", run)
    assert await sources._run_claimed_sync(sid, "obsolete") == {"status": "superseded"}
    assert await sources._run_claimed_sync(sid, task_id) == {"status": "done"}
    assert await sources._run_claimed_sync(sid, task_id) == {"status": "superseded"}
    run.assert_awaited_once_with(sid)


@pytest.mark.asyncio
async def test_scheduler_ticks_do_not_multiply_waiting_jobs(client, pool, monkeypatch):
    _, sid = await make_source(client)
    published = []
    monkeypatch.setattr(
        source_sync_service.celery, "send_task", lambda *a, **kw: published.append(kw)
    )
    assert await sources._reconcile_due() == 1
    await pool.execute(
        "UPDATE user_sources SET next_sync_at = now() - interval '1 hour' WHERE id=$1", sid
    )
    assert await sources._reconcile_due() == 0
    # Reclaim only after the worker's hard limit, then discard the old delivery.
    old = published[0]["task_id"]
    await pool.execute(
        "UPDATE user_sources SET sync_claimed_at = now() - interval '36 minutes' WHERE id=$1", sid
    )
    assert await sources._reconcile_due() == 1
    assert not await source_sync_service.start_sync(sid, old)
    assert len(published) == 2


@pytest.mark.asyncio
async def test_repeated_manual_sync_is_rejected_without_new_job(client, monkeypatch):
    key, sid = await make_source(client)
    published = []
    monkeypatch.setattr(
        source_sync_service.celery, "send_task", lambda *a, **kw: published.append(kw)
    )
    first = await client.post(f"/api/v1/me/sources/{sid}/sync", headers=_auth(key))
    second = await client.post(f"/api/v1/me/sources/{sid}/sync", headers=_auth(key))
    assert first.status_code == 200
    assert second.status_code == 409
    assert len(published) == 1


@pytest.mark.asyncio
async def test_broker_failure_releases_claim_for_retry(client, pool, monkeypatch):
    _, sid = await make_source(client)

    def fail(*a, **kw):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(source_sync_service.celery, "send_task", fail)
    with pytest.raises(ConnectionError):
        await source_sync_service.enqueue_sync(sid)
    row = await pool.fetchrow("SELECT sync_task_id,sync_status FROM user_sources WHERE id=$1", sid)
    assert row["sync_task_id"] is None
    assert row["sync_status"] == "failed"
    assert [UUID(s["id"]) for s in await source_service.due_sources()] == [sid]


@pytest.mark.asyncio
async def test_failed_alert_is_retried_and_successful_alert_is_rate_limited(
    client, pool, monkeypatch
):
    _, sid = await make_source(client)
    await pool.execute(
        "UPDATE user_sources SET created_at = now() - interval '2 hours' WHERE id=$1", sid
    )
    send = AsyncMock(side_effect=ConnectionError("webhook down"))
    monkeypatch.setattr(alert_service, "send_alert", send)
    with pytest.raises(ConnectionError):
        await sources._alert_stalled_syncs()
    assert await pool.fetchval("SELECT sync_alerted_at FROM user_sources WHERE id=$1", sid) is None
    send.side_effect = None
    assert await sources._alert_stalled_syncs() == 1
    assert "Skills" in send.call_args.args[0]
    assert await sources._alert_stalled_syncs() == 0


@pytest.mark.asyncio
async def test_watchdog_catches_queued_work_even_after_recent_success(client, pool, monkeypatch):
    _, sid = await make_source(client)
    await pool.execute(
        "UPDATE user_sources SET last_synced_at=now(), sync_task_id='waiting', "
        "sync_claimed_at=now()-interval '16 minutes' WHERE id=$1",
        sid,
    )
    send = AsyncMock()
    monkeypatch.setattr(alert_service, "send_alert", send)
    assert await sources._alert_stalled_syncs() == 1
    assert str(sid) in send.call_args.args[0]


@pytest.mark.asyncio
async def test_healthy_and_disabled_sources_do_not_alert(client, pool, monkeypatch):
    _, sid = await make_source(client)
    send = AsyncMock()
    monkeypatch.setattr(alert_service, "send_alert", send)
    assert await sources._alert_stalled_syncs() == 0
    await pool.execute(
        "UPDATE user_sources SET created_at=now()-interval '2 hours', sync_enabled=false WHERE id=$1",
        sid,
    )
    assert await sources._alert_stalled_syncs() == 0
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_alert_destination_fails_loudly(client, monkeypatch):
    monkeypatch.setattr(settings, "ALERT_SLACK_TEAM_ID", None)
    with pytest.raises(RuntimeError, match="required"):
        await alert_service.send_alert("Sync freshness test")


@pytest.mark.asyncio
async def test_duplicate_delivery_cannot_run_alongside_active_worker(client, monkeypatch):
    _, sid = await make_source(client)
    monkeypatch.setattr(source_sync_service.celery, "send_task", lambda *a, **kw: None)
    task_id = await source_sync_service.enqueue_sync(sid)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def run(_):
        entered.set()
        await release.wait()
        return {"status": "done"}

    monkeypatch.setattr(sources, "_sync_source", run)
    first = asyncio.create_task(sources._run_claimed_sync(sid, task_id))
    await entered.wait()
    try:
        assert await sources._run_claimed_sync(sid, task_id) == {"status": "superseded"}
        assert await source_sync_service.enqueue_sync(sid) is None
    finally:
        release.set()
        await first


@pytest.mark.asyncio
async def test_alert_requires_slack_acceptance(client, monkeypatch):
    import httpx

    from backend.integrations.slack import client as slack_client
    from backend.integrations.slack import installs

    monkeypatch.setattr(settings, "ALERT_SLACK_TEAM_ID", "T_STASH")
    monkeypatch.setattr(settings, "ALERT_SLACK_CHANNEL_ID", "C_INCIDENTS")
    monkeypatch.setattr(
        installs, "get_install", AsyncMock(return_value={"bot_token": "test-token"})
    )
    real_client = httpx.AsyncClient
    delivered = []

    def receive(request):
        delivered.append(request.read())
        return httpx.Response(200, json={"ok": False, "error": "not_in_channel"})

    monkeypatch.setattr(
        slack_client.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(receive), **kw),
    )
    with pytest.raises(RuntimeError, match="not_in_channel"):
        await alert_service.send_alert("Sync test")
    assert delivered == [b'{"channel":"C_INCIDENTS","text":"Sync test"}']


@pytest.mark.asyncio
async def test_alert_uses_the_configured_workspace_and_channel(client, monkeypatch):
    from backend.integrations.slack import client as slack_client
    from backend.integrations.slack import installs

    monkeypatch.setattr(settings, "ALERT_SLACK_TEAM_ID", "T_STASH")
    monkeypatch.setattr(settings, "ALERT_SLACK_CHANNEL_ID", "C_INCIDENTS")
    install = AsyncMock(return_value={"bot_token": "test-token"})
    post = AsyncMock()
    monkeypatch.setattr(installs, "get_install", install)
    monkeypatch.setattr(slack_client, "post_message", post)
    await alert_service.send_alert("Sync freshness alert")
    install.assert_awaited_once_with("T_STASH")
    post.assert_awaited_once_with("test-token", "C_INCIDENTS", "Sync freshness alert")
