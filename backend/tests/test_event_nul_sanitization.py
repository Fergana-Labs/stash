"""NUL bytes in event payloads must never cause a 500.

Postgres cannot store NUL (0x00) in text/jsonb. Agents send it in practice
(e.g. a tool-output preview of grepping a binary), and a payload that
500s deterministically wedges the plugin's retry queue behind it: the
client treats 5xx as "transient, retry later", so the contract is that
the backend never returns a payload-dependent 500.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("nul"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['api_key']}"}


@pytest.mark.asyncio
async def test_event_with_nul_bytes_is_accepted_and_stripped(client: AsyncClient):
    headers = await _register(client)
    resp = await client.post(
        "/api/v1/me/sessions/events",
        json={
            "agent_name": "tester",
            "event_type": "tool_use",
            "content": "Ran: grep binary\x00output",
            "session_id": "nul-session",
            "tool_name": "bash\x00",
            "metadata": {"response_preview": "junk\x00\x00bytes", "nested": {"k\x00ey": ["v\x00"]}},
        },
        headers=headers,
    )
    assert resp.status_code == 201
    event = resp.json()
    assert event["content"] == "Ran: grep binaryoutput"
    assert event["tool_name"] == "bash"
    assert event["metadata"]["response_preview"] == "junkbytes"
    assert event["metadata"]["nested"] == {"key": ["v"]}


@pytest.mark.asyncio
async def test_batch_event_with_nul_bytes_is_accepted_and_stripped(client: AsyncClient):
    headers = await _register(client)
    resp = await client.post(
        "/api/v1/me/sessions/events/batch",
        json={
            "events": [
                {
                    "agent_name": "tester",
                    "event_type": "tool_use",
                    "content": "clean event",
                    "session_id": "nul-batch-session",
                },
                {
                    "agent_name": "tester",
                    "event_type": "tool_use",
                    "content": "dirty\x00event",
                    "session_id": "nul-batch-session",
                    "metadata": {"preview": "\x00\x00"},
                },
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 201
    events = resp.json()
    assert [e["content"] for e in events] == ["clean event", "dirtyevent"]
    assert events[1]["metadata"] == {"preview": ""}
