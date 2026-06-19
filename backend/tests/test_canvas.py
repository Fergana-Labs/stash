"""Canvas (generative-UI) wiring tests.

These pin the contract the frontend relies on: the canvas tools are registered
and exposed to the in-app agent (but withheld from Slack, which can't render
UI), the chat surface advertises the canvas in its system prompt, and a canvas
tool result is turned into the `canvas` stream event that opens the panel.
"""

import pytest
from httpx import AsyncClient

from backend.services import agent_runtime, prompts, tool_loop

from .conftest import unique_name

CANVAS_TOOLS = ("create_canvas", "update_canvas", "read_canvas", "list_canvases")


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("canvas"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def test_canvas_tools_registered_and_callable():
    for name in CANVAS_TOOLS:
        assert name in agent_runtime._TOOLS_BY_NAME
        assert name in prompts.STASH_TOOL_SET


def test_canvas_tools_hidden_from_slack_and_readonly_ask():
    # Slack has nowhere to render the panel; the read-only ask surface must not
    # be able to mutate workspace state by creating canvases.
    for name in CANVAS_TOOLS:
        assert name not in prompts.SLACK_TOOL_SET
        assert name not in prompts.ASK_TOOL_SET


def test_chat_system_prompt_advertises_canvas_only_when_ui_available():
    # The canvas only exists on a surface that can render it, so the agent must
    # only be told about it there — otherwise it offers a tool it can't use.
    with_ui = prompts.render_ask_system("Acme", can_render_ui=True)
    without_ui = prompts.render_ask_system("Acme", can_render_ui=False)
    assert "create_canvas" in with_ui
    assert "create_canvas" not in without_ui


def test_canvas_event_built_from_tool_result():
    event = tool_loop._canvas_event("create_canvas", '{"id": "abc-123", "title": "Q2"}')
    assert event == {"type": "canvas", "id": "abc-123", "name": "create_canvas"}


def test_canvas_event_none_when_no_id_or_bad_json():
    assert tool_loop._canvas_event("create_canvas", '{"error": "boom"}') is None
    assert tool_loop._canvas_event("update_canvas", "not json") is None


@pytest.mark.asyncio
async def test_canvas_crud_via_api(client: AsyncClient):
    """A canvas is a real workspace object: create, list (by session), update,
    and resolve by id alone (the link the chat stream hands the panel)."""
    api_key = await _register(client)
    headers = _auth(api_key)
    ws = await client.post("/api/v1/workspaces", json={"name": "Canvas WS"}, headers=headers)
    assert ws.status_code == 201
    ws_id = ws.json()["id"]

    create = await client.post(
        f"/api/v1/workspaces/{ws_id}/canvases",
        json={
            "title": "Sales",
            "session_id": "agent-xyz",
            "blocks": [{"type": "heading", "text": "Q2"}],
        },
        headers=headers,
    )
    assert create.status_code == 200, create.text
    canvas = create.json()
    assert canvas["title"] == "Sales"
    assert canvas["blocks"][0]["text"] == "Q2"

    by_session = await client.get(
        f"/api/v1/workspaces/{ws_id}/canvases?session_id=agent-xyz", headers=headers
    )
    assert [c["id"] for c in by_session.json()["canvases"]] == [canvas["id"]]

    updated = await client.patch(
        f"/api/v1/workspaces/{ws_id}/canvases/{canvas['id']}",
        json={"blocks": [{"type": "text", "text": "done"}]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["blocks"] == [{"type": "text", "text": "done"}]

    fetched = await client.get(f"/api/v1/canvases/{canvas['id']}", headers=headers)
    assert fetched.json()["blocks"][0]["text"] == "done"


@pytest.mark.asyncio
async def test_canvas_hidden_from_non_members(client: AsyncClient):
    owner = _auth(await _register(client))
    ws = await client.post("/api/v1/workspaces", json={"name": "Private"}, headers=owner)
    ws_id = ws.json()["id"]
    canvas = await client.post(
        f"/api/v1/workspaces/{ws_id}/canvases",
        json={"title": "Secret", "blocks": []},
        headers=owner,
    )
    canvas_id = canvas.json()["id"]

    outsider = _auth(await _register(client))
    # Unscoped lookup must 404 (not 403) so it can't confirm the canvas exists.
    resp = await client.get(f"/api/v1/canvases/{canvas_id}", headers=outsider)
    assert resp.status_code == 404
