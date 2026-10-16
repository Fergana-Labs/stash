"""Ephemeral, account-bound RPC to a user's read-only local history connector."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import redis.asyncio as redis

from stashai.local_history import MAX_RESULT, validate_request

from ...config import settings

TTL = 45


def _key(owner: UUID, suffix: str) -> str:
    return f"wizard-history:{owner}:{suffix}"


def _redis():
    # Per-operation context avoids sharing async clients across test event loops.
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


async def status(owner: UUID) -> dict:
    async with _redis() as client:
        active = await client.get(_key(owner, "active"))
    return {"connected": bool(active)}


async def poll(owner: UUID, device_id: UUID) -> dict:
    device = str(device_id)
    async with _redis() as client:
        key = _key(owner, "active")
        acquired = await client.set(key, device, nx=True, ex=TTL)
        if not acquired:
            refreshed = await client.eval(
                "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end",
                1,
                key,
                device,
                TTL,
            )
            if not refreshed:
                raise ValueError(
                    "Another local history connector is already connected to this account"
                )
        queue = _key(owner, f"queue:{device}")
        for _ in range(20):
            request_id = await client.lpop(queue)
            if not request_id:
                return {"request": None}
            payload = await client.get(_key(owner, f"pending:{request_id}"))
            if payload:
                return {"request": json.loads(payload)}
    return {"request": None}


async def complete(owner: UUID, device_id: UUID, request_id: UUID, result: dict) -> None:
    encoded = json.dumps(result)
    if len(encoded) > MAX_RESULT:
        raise ValueError("Local history response is too large")
    async with _redis() as client:
        pending = await client.get(_key(owner, f"pending:{request_id}"))
        if not pending or json.loads(pending)["device_id"] != str(device_id):
            raise LookupError("History request not found or expired")
        # First delivery wins; stale/duplicate responses cannot replace it.
        await client.set(_key(owner, f"result:{request_id}"), encoded, ex=TTL, nx=True)


async def request(owner: UUID, operation: str, args: dict, *, timeout: float = 15) -> dict:
    args = validate_request(operation, args)
    request_id = uuid4()
    pending_key = _key(owner, f"pending:{request_id}")
    result_key = _key(owner, f"result:{request_id}")
    async with _redis() as client:
        device = await client.get(_key(owner, "active"))
        if not device:
            return {
                "connected": False,
                "results": [],
                "message": "Local history is disconnected. Run stash history-bridge on the computer with your Codex sessions; no import is needed.",
            }
        payload = {"id": str(request_id), "device_id": device, "operation": operation, "args": args}
        queue = _key(owner, f"queue:{device}")
        await client.set(pending_key, json.dumps(payload), ex=TTL)
        await client.rpush(queue, str(request_id))
        await client.expire(queue, TTL)
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            while asyncio.get_running_loop().time() < deadline:
                raw = await client.get(result_key)
                if raw:
                    result = json.loads(raw)
                    if result.get("error"):
                        raise ValueError(
                            "Local history could not complete this request: "
                            + str(result["error"])[:200]
                        )
                    return {**result, "connected": True}
                await asyncio.sleep(0.2)
            return {
                "connected": True,
                "results": [],
                "unavailable": True,
                "message": "The local history connector did not respond in time. Retry a narrower search; do not claim there were no matches.",
            }
        finally:
            await client.delete(pending_key, result_key)
