"""Exercise tool discovery/validation and the authenticated HTTP contract through MCP."""

import json
from uuid import uuid4

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from cli import mcp_server
from cli.client import StashClient

EVAL_ID = str(uuid4())
TRAIT = {"name": "Useful work", "good": "Completes the task", "bad": "Stops at a plan"}


@pytest.fixture
def api(monkeypatch):
    requests = []
    responses = []

    def handle(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["x-stash-scope"] == "test-workspace"
        status, payload = responses.pop(0)
        return httpx.Response(status, json=payload)

    def client():
        result = StashClient("https://example.test", "test-key", scope="test-workspace")
        result._http.close()
        result._http = httpx.Client(
            base_url="https://example.test", transport=httpx.MockTransport(handle)
        )
        return result

    monkeypatch.setattr(mcp_server, "_client", client)
    return requests, responses


async def call(tool_name, **arguments):
    content, _ = await mcp_server.mcp.call_tool(f"stash_reward_function_{tool_name}", arguments)
    return json.loads(content[0].text)


async def test_discovery_exposes_rubric_schema_and_version_requirement():
    tools = {tool.name: tool for tool in await mcp_server.mcp.list_tools()}
    schema = tools["stash_reward_function_create"].inputSchema
    assert schema["required"] == ["name", "instructions", "traits"]
    assert schema["properties"]["traits"]["minItems"] == 1
    assert schema["properties"]["traits"]["maxItems"] == 12
    assert schema["$defs"]["RewardFunctionTrait"]["required"] == ["name", "good", "bad"]
    assert "base_version" in tools["stash_reward_function_set_rubric"].inputSchema["required"]
    assert all(f"stash_reward_function_{name}" in tools for name in ("list", "get", "score"))


async def test_create_saves_rubric_and_returns_ready_function(api):
    requests, responses = api
    ready = {"id": EVAL_ID, "ready": True, "version": 1, "traits": [TRAIT]}
    responses.extend([(201, {"id": EVAL_ID, "ready": False}), (200, {}), (200, ready)])
    assert (
        await call("create", name="Knowledge work", instructions="Be accurate", traits=[TRAIT])
        == ready
    )
    assert [(r.method, r.url.path) for r in requests] == [
        ("POST", "/api/v1/evals"),
        ("PUT", f"/api/v1/evals/{EVAL_ID}/rubric"),
        ("GET", f"/api/v1/evals/{EVAL_ID}"),
    ]
    assert json.loads(requests[0].content) == {
        "name": "Knowledge work",
        "instructions": "Be accurate",
    }
    assert json.loads(requests[1].content) == {"base": 0, "traits": [{**TRAIT, "basis": ""}]}


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "  "},
        {"instructions": "x" * 2001},
        {"traits": []},
        {"traits": [TRAIT] * 13},
        {"traits": [{**TRAIT, "name": "  "}]},
        {"traits": [{**TRAIT, "good": "x" * 401}]},
        {"traits": [{**TRAIT, "unknown": "field"}]},
        {"traits": [TRAIT, {**TRAIT, "name": " useful WORK "}]},
    ],
)
async def test_invalid_create_does_not_leave_an_empty_eval(api, changes):
    requests, _ = api
    arguments = {"name": "Knowledge work", "instructions": "Be accurate", "traits": [TRAIT]}
    with pytest.raises(ToolError):
        await call("create", **(arguments | changes))
    assert requests == []


async def test_partial_creation_reports_recoverable_id_without_retry_or_delete(api):
    requests, responses = api
    responses.extend([(201, {"id": EVAL_ID}), (503, {"detail": "temporarily unavailable"})])
    with pytest.raises(ToolError, match=f"Reward function {EVAL_ID} was created"):
        await call("create", name="Knowledge work", instructions="Be accurate", traits=[TRAIT])
    assert [r.method for r in requests] == ["POST", "PUT"]


async def test_set_rubric_preserves_concurrency_guard_and_reports_conflict(api):
    requests, responses = api
    responses.append((409, {"detail": "The rubric changed while you were editing"}))
    with pytest.raises(ToolError, match="rubric changed"):
        await call("set_rubric", eval_id=EVAL_ID, traits=[TRAIT], base_version=7)
    assert len(requests) == 1
    assert json.loads(requests[0].content)["base"] == 7


@pytest.mark.parametrize("name", ["get", "set_rubric", "score"])
async def test_invalid_ids_rejected_before_http(api, name):
    requests, _ = api
    args = {"eval_id": "../other"}
    if name == "set_rubric":
        args.update(traits=[TRAIT], base_version=0)
    if name == "score":
        args["output"] = {"text": "answer"}
    with pytest.raises(ToolError):
        await call(name, **args)
    assert not requests


async def test_list_and_get_use_existing_owner_scoped_endpoints(api):
    requests, responses = api
    responses.extend([(200, {"evals": [{"id": EVAL_ID}]}), (404, {"detail": "Eval not found"})])
    assert await call("list") == {"evals": [{"id": EVAL_ID}]}
    with pytest.raises(ToolError, match="Eval not found"):
        await call("get", eval_id=EVAL_ID)
    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/api/v1/evals"),
        ("GET", f"/api/v1/evals/{EVAL_ID}"),
    ]


async def test_score_preserves_output_context_and_change_input(api):
    requests, responses = api
    responses.append((200, {"call_id": "call", "score": 0.0, "fixes": [{"fix": "Use plain text"}]}))
    result = await call(
        "score",
        eval_id=EVAL_ID,
        output={"text": "Monday \u00b7 9 PM", "images": ["data:image/png;base64,AA=="]},
        trace=[{"role": "user", "content": "Write the event details"}],
        change="Edit the event header",
        before={"text": "Monday, 9 PM"},
        caller="test-agent",
        ref="task-1",
    )
    assert result["score"] == 0.0
    body = json.loads(requests[0].content)
    assert body["output"]["text"] == "Monday \u00b7 9 PM"
    assert body["output"]["images"] == ["data:image/png;base64,AA=="]
    assert body["trace"][0]["role"] == "user"
    assert body["before"] == {"text": "Monday, 9 PM", "images": []}
    assert body["change"] == "Edit the event header"
    assert body["caller"] == "test-agent" and body["ref"] == "task-1"
    assert requests[0].extensions["timeout"]["read"] == 180
    assert len(requests) == 1  # Scoring does not create examples or train anything.


async def test_score_surfaces_provider_error_without_fabricating_grade(api):
    _, responses = api
    responses.append((503, {"detail": "Judge unavailable"}))
    with pytest.raises(ToolError, match="Judge unavailable"):
        await call("score", eval_id=EVAL_ID, output={"text": "answer"})
