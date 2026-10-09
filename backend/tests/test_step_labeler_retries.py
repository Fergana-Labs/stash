"""Provider throttling retries a chunk without restarting the whole trace."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import uuid4

import httpx
import pytest

from backend.config import settings
from backend.services.rm import step_labeler, step_labeling


@pytest.fixture
def sleeps(monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(step_labeler.asyncio, "sleep", sleep)
    monkeypatch.setattr(step_labeler.random, "uniform", lambda low, high: 0.5)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test")
    return delays


def limited(*, headers=None, code="rate_limit_exceeded"):
    return httpx.Response(429, headers=headers, json={"error": {"code": code}})


async def test_rate_limit_keeps_other_chunk_labels(monkeypatch, sleeps):
    calls = Counter()
    bodies = []

    def respond(request):
        body = json.loads(request.content)
        chunk_id = body["input"][-1]["content"].split()[2]
        calls[chunk_id] += 1
        if chunk_id == "a2":
            bodies.append(body)
            if calls[chunk_id] == 1:
                return limited(headers={"retry-after": "7"})
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"text": json.dumps({"intent": None})}],
                    }
                ]
            },
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        step_labeling.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    chunks = [
        {
            "chunk_id": f"a{i}",
            "actor": "agent",
            "kind": "agent_message",
            "idx": i,
            "text": f"message {i}",
        }
        for i in range(3)
    ]
    labels = await step_labeling.label_steps(uuid4(), chunks, {})
    assert set(labels) == {"a0", "a1", "a2"}
    assert calls == {"a0": 1, "a1": 1, "a2": 2}
    assert bodies[0] == bodies[1]  # Preserve the target, transcript and cache key.
    assert sleeps == [7.5]


async def test_persistent_rate_limit_stops_after_bounded_retries(sleeps):
    requests = []

    def respond(request):
        requests.append(request)
        return limited()

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(step_labeler.LabelingError, match="returned 429"):
            await step_labeler.label_chunk(
                client, "cache", "transcript", {"chunk_id": "a1", "actor": "agent"}
            )
    assert len(requests) == 5
    assert sleeps == [5.5, 10.5, 20.5, 40.5]


@pytest.mark.parametrize(
    "status,code",
    [
        (429, "insufficient_quota"),
        (429, "billing_hard_limit_reached"),
        (401, "invalid_api_key"),
        (500, "server_error"),
    ],
)
async def test_quota_and_other_failures_surface_without_extra_requests(sleeps, status, code):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": code}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(step_labeler.LabelingError, match=f"returned {status}"):
            await step_labeler.label_chunk(
                client, "cache", "transcript", {"chunk_id": "a1", "actor": "agent"}
            )
    assert len(calls) == 1 and sleeps == []


def test_retry_headers_respect_provider_delay_and_bound_waits(sleeps):
    assert step_labeler.rate_limit_delay(limited(headers={"retry-after-ms": "9000"}), 0) == 9.5
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=90))
    assert 89 <= step_labeler.rate_limit_delay(limited(headers={"retry-after": future}), 0) <= 91
    assert step_labeler.rate_limit_delay(limited(headers={"retry-after": "121"}), 0) is None
    for value in ("bad header", "NaN", "Infinity", "-1", "0"):
        assert step_labeler.rate_limit_delay(limited(headers={"retry-after": value}), 0) == 5.5
