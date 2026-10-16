import asyncio
from uuid import uuid4

import pytest

from backend.auth import create_api_key
from backend.services.intuition import history_bridge

from .conftest import unique_name


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.queues = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, *, nx=False, ex=None):
        assert ex == history_bridge.TTL
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script, n, key, device, ttl):
        return int(self.values.get(key) == device)

    async def expire(self, key, ttl):
        assert ttl == history_bridge.TTL

    async def lpop(self, key):
        queue = self.queues.setdefault(key, [])
        return queue.pop(0) if queue else None

    async def rpush(self, key, value):
        self.queues.setdefault(key, []).append(value)

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(history_bridge, "_redis", lambda: fake)
    return fake


async def test_local_requests_results_and_devices_are_account_bound(redis):
    owner, stranger, device = uuid4(), uuid4(), uuid4()
    await history_bridge.poll(owner, device)
    task = asyncio.create_task(
        history_bridge.request(owner, "search", {"query": "website"}, timeout=2)
    )
    await asyncio.sleep(0)
    assert (await history_bridge.poll(stranger, uuid4()))["request"] is None
    request = (await history_bridge.poll(owner, device))["request"]
    request_id = request["id"]
    assert request["operation"] == "search" and request["args"]["query"] == "website"
    with pytest.raises(LookupError):
        await history_bridge.complete(stranger, device, request_id, {"results": []})
    with pytest.raises(LookupError):
        await history_bridge.complete(owner, uuid4(), request_id, {"results": []})
    await history_bridge.complete(owner, device, request_id, {"results": [{"id": "real"}]})
    await history_bridge.complete(owner, device, request_id, {"results": [{"id": "replacement"}]})
    result = await task
    assert result == {"results": [{"id": "real"}], "connected": True}
    assert not any(":pending:" in key or ":result:" in key for key in redis.values)
    with pytest.raises(LookupError):
        await history_bridge.complete(owner, device, request_id, {"results": []})


async def test_disconnected_and_timed_out_are_not_reported_as_no_matches(redis):
    owner, device = uuid4(), uuid4()
    result = await history_bridge.request(owner, "search", {})
    assert result["connected"] is False and "no import" in result["message"]
    await history_bridge.poll(owner, device)
    with pytest.raises(ValueError, match="already connected"):
        await history_bridge.poll(owner, uuid4())
    result = await history_bridge.request(owner, "search", {}, timeout=0)
    assert result["unavailable"] and result["connected"]
    assert not any(":pending:" in key for key in redis.values)


async def test_authenticated_read_key_can_connect_but_other_accounts_cannot_answer(client, redis):
    from uuid import UUID

    async def account():
        response = await client.post(
            "/api/v1/users/register",
            json={"name": unique_name("bridge"), "password": "securepassword1"},
        )
        return UUID(response.json()["id"]), {
            "Authorization": "Bearer " + response.json()["api_key"]
        }

    owner, _ = await account()
    _, other_headers = await account()
    key = await create_api_key(owner, name="Read-only connector", access="read")
    headers = {"Authorization": "Bearer " + key}
    device = str(uuid4())
    prefix = "/api/v1/model-wizard/history/local"
    assert (await client.post(prefix + "/poll", json={"device_id": device})).status_code == 401
    response = await client.post(prefix + "/poll", headers=headers, json={"device_id": device})
    assert response.status_code == 200, response.text
    assert (
        await client.post("/api/v1/model-wizard/sessions", headers=headers, json={})
    ).status_code == 403
    task = asyncio.create_task(history_bridge.request(owner, "search", {}, timeout=5))
    await asyncio.sleep(0)
    response = await client.post(prefix + "/poll", headers=headers, json={"device_id": device})
    rid = response.json()["request"]["id"]
    result = {"device_id": device, "result": {"results": []}}
    assert (
        await client.post(prefix + "/results/" + rid, headers=other_headers, json=result)
    ).status_code == 404
    assert (
        await client.post(prefix + "/results/" + rid, headers=headers, json=result)
    ).status_code == 204
    assert (await task)["connected"]
