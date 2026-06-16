"""Tests for the realtime change-feed bus and the row-event hooks."""

import json
import uuid

import pytest
from httpx import AsyncClient

from backend.services import realtime


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_dispatch_and_unsubscribe():
    key = "table:unit-test"
    q = realtime.subscribe(key)
    realtime._dispatch_local(key, {"type": "row.created", "row_id": "1"})
    assert q.get_nowait() == {"type": "row.created", "row_id": "1"}

    realtime.unsubscribe(key, q)
    realtime._dispatch_local(key, {"type": "row.created", "row_id": "2"})
    assert q.empty()  # no longer subscribed


def test_on_notify_dedupes_own_origin():
    key = "table:dedupe-test"
    q = realtime.subscribe(key)
    try:
        # An event this process emitted (same origin) was already dispatched locally.
        realtime._on_notify(None, 0, realtime.CHANNEL,
                            json.dumps({"origin": realtime._ORIGIN, "key": key, "event": {"a": 1}}))
        assert q.empty()
        # An event from another instance is dispatched.
        realtime._on_notify(None, 0, realtime.CHANNEL,
                            json.dumps({"origin": "other", "key": key, "event": {"a": 2}}))
        assert q.get_nowait() == {"a": 2}
    finally:
        realtime.unsubscribe(key, q)


@pytest.mark.asyncio
async def test_row_create_emits_event(client: AsyncClient):
    name = f"user_{uuid.uuid4().hex[:10]}"
    api_key = (
        await client.post(
            "/api/v1/users/register",
            json={"name": name, "display_name": name, "password": "password123"},
        )
    ).json()["api_key"]
    ws = (await client.post("/api/v1/workspaces", json={"name": "RT"}, headers=_auth(api_key))).json()
    table = (
        await client.post(
            f"/api/v1/workspaces/{ws['id']}/tables",
            json={"name": "Events", "columns": [{"name": "Title", "type": "text"}]},
            headers=_auth(api_key),
        )
    ).json()

    q = realtime.subscribe(realtime.table_key(table["id"]))
    try:
        hdr = {**_auth(api_key), "X-Stash-Workspace": ws["id"]}
        created = await client.post("/rest/v1/Events", json={"Title": "Hi"}, headers=hdr)
        assert created.status_code == 201
        event = q.get_nowait()  # dispatched synchronously on emit
        assert event["type"] == "row.created"
        assert event["row_id"] == created.json()["id"]
    finally:
        realtime.unsubscribe(realtime.table_key(table["id"]), q)
