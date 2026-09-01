"""The HTTP side of talking to a GPU app on Modal.

Every kind deploys one Modal app with a single web endpoint that takes
`{"op": ..., ...}` and either spawns a job (`*_start` ops, returning a
`call_id`) or reports on one (`result`, returning 202 while it runs). The
backend never imports the Modal SDK: the GPU code is deployed from `gpu/`
on its own schedule, and this client only needs a URL and the shared secret
both sides hold.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from ..config import settings


class GpuJobFailed(Exception):
    """The GPU job raised. The message is Modal's error text."""


def _headers() -> dict[str, str]:
    if not settings.STYLEWRITER_GPU_SECRET:
        raise RuntimeError("STYLEWRITER_GPU_SECRET must be set to reach the GPU app")
    return {"Authorization": f"Bearer {settings.STYLEWRITER_GPU_SECRET}"}


async def start(url: str, op: str, payload: dict) -> str:
    """Spawn a job; the call id is what `result` is polled with."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json={"op": op, **payload}, headers=_headers())
    if response.status_code == 400:
        raise ValueError(response.json()["detail"])
    response.raise_for_status()
    return response.json()["call_id"]


async def call(url: str, op: str, payload: dict) -> dict:
    """An op the endpoint answers inline, without spawning a job."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json={"op": op, **payload}, headers=_headers())
    if response.status_code == 400:
        raise ValueError(response.json()["detail"])
    response.raise_for_status()
    return response.json()


async def result(url: str, call_id: str) -> dict | None:
    """The job's result, or None while it is still running."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            url, json={"op": "result", "call_id": call_id}, headers=_headers()
        )
    if response.status_code == 202:
        return None
    if response.status_code == 500:
        raise GpuJobFailed(response.json()["detail"])
    response.raise_for_status()
    return response.json()


async def wait(url: str, call_id: str, seconds: float, every: float = 2.0) -> dict | None:
    """Poll for up to `seconds`; None means it is still running after that."""
    deadline = time.monotonic() + seconds
    while True:
        found = await result(url, call_id)
        if found is not None:
            return found
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(every)
