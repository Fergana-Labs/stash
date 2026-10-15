"""The intuitions MCP server: JSON-RPC over streamable HTTP, authenticated like the REST API."""

import json
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from backend.routers import intuition_mcp

from .test_model_wizard import _auth

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@asynccontextmanager
async def mcp_client():
    # Each session manager runs once; build a fresh one for this test's app. (A context
    # manager, not a fixture: its task group must open and close in the same task.)
    intuition_mcp.mcp._session_manager = None
    app = intuition_mcp.mcp.streamable_http_app()
    async with intuition_mcp.mcp.session_manager.run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


async def _rpc(client, method, params, auth=None, n=[0]):
    n[0] += 1
    resp = await client.post(
        "/intuitions",
        headers={**HEADERS, **(auth or {})},
        json={"jsonrpc": "2.0", "id": n[0], "method": method, "params": params},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


async def _call(client, auth, tool, args):
    result = await _rpc(client, "tools/call", {"name": tool, "arguments": args}, auth)
    if result.get("isError"):
        return True, result["content"][0]["text"]
    structured = result.get("structuredContent")
    if structured is not None:
        return False, structured.get("result", structured)
    return False, json.loads(result["content"][0]["text"])


async def test_tools_build_and_list_an_intuition(client):
    async with mcp_client() as mcp:
        await _build_and_list(client, mcp)


async def test_mcp_updates_keep_the_brief_and_agent_judge_and_enforce_ownership(client):
    auth = await _auth(client)
    other = await _auth(client)
    created = await client.post(
        "/api/v1/intuitions",
        headers=auth,
        json={
            "name": "Slide issues",
            "output_type": "multi",
            "description": "Review this slide",
            "labels": [{"id": "unreadable"}, {"id": "unsupported"}],
            "rubric": [],
        },
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["model"]["id"]
    switched = await client.patch(
        f"/api/v1/intuitions/{model_id}/draft",
        headers=auth,
        json={"provider": "agent_judge"},
    )
    assert switched.status_code == 200, switched.text
    async with mcp_client() as mcp:
        err, _ = await _call(
            mcp,
            auth,
            "save_brief",
            {
                "intuition_id": model_id,
                "fields": {"costly_mistake": "Approving a misleading slide"},
            },
        )
        assert not err
        err, result = await _call(
            mcp,
            auth,
            "update_intuition",
            {
                "intuition_id": model_id,
                "name": "Client slides",
                "instructions": "Check the evidence",
            },
        )
        assert not err, result
        err, _ = await _call(
            mcp,
            other,
            "update_intuition",
            {"intuition_id": model_id, "name": "Not mine"},
        )
        assert err
    detail = (await client.get(f"/api/v1/intuitions/{model_id}", headers=auth)).json()
    assert detail["model"]["name"] == "Client slides"
    assert detail["draft"]["provider"] == "agent_judge"
    assert detail["draft"]["description"].startswith("Check the evidence")
    assert "Approving a misleading slide" in detail["draft"]["description"]


async def _build_and_list(client, mcp_client):
    auth = await _auth(client)
    tools = {t["name"] for t in (await _rpc(mcp_client, "tools/list", {}, auth))["tools"]}
    assert {
        "create_intuition",
        "save_brief",
        "generate_examples",
        "train",
        "classify",
        "review_prediction",
    } <= tools

    err, created = await _call(
        mcp_client,
        auth,
        "create_intuition",
        {
            "name": "Photo issues",
            "output_type": "multi",
            "instructions": "Which guidelines does the photo break?",
            "labels": [
                {"id": "background", "description": "Not white"},
                {"id": "watermark", "description": "Overlaid logo"},
            ],
            "brief": {"costly_mistake": "Missing a watermark"},
        },
    )
    assert not err, created
    model_id = created["id"]
    assert created["status"]["brief"] == {"costly_mistake": "Missing a watermark"}
    err, added = await _call(
        mcp_client,
        auth,
        "add_examples",
        {
            "intuition_id": model_id,
            "examples": [
                {"item": "logo over a wood table", "label": "watermark+background", "pinned": True},
                {"item": "clean shot"},
            ],
        },
    )
    assert not err and added["added"] == 2
    err, examples = await _call(mcp_client, auth, "list_examples", {"intuition_id": model_id})
    assert sorted((e["label"] or "", e["pinned"]) for e in examples) == [
        ("", False),
        ("background+watermark", True),
    ]
    err, listed = await _call(mcp_client, auth, "list_intuitions", {})
    assert [m["name"] for m in listed] == ["Photo issues"]

    # No bearer token: the tool fails, it does not run anonymously.
    err, message = await _call(mcp_client, None, "list_intuitions", {})
    assert err and "Bearer" in message
