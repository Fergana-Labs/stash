"""Reward model platform API: import, annotate, export, query, jobs, owner isolation."""

import json
import time

import pytest
from httpx import AsyncClient

from backend.services.rm import query
from backend.tasks import reward_models as rm_tasks

from .conftest import unique_name

pytestmark = pytest.mark.usefixtures("rm_title_generator")


@pytest.fixture(autouse=True)
def training_runtime(monkeypatch):
    monkeypatch.setenv("RM_COMPUTE", "local")


REFUND_TRACE = {
    "id": "refund-1182",
    "title": "Refund request for order 1182",
    "metadata": {"agent": "support-bot"},
    "steps": [
        {"role": "system", "content": "You are a support agent."},
        {"role": "user", "content": "I want a refund for order 1182"},
        {
            "role": "assistant",
            "content": "",
            "tool_name": "lookup_order",
            "tool_input": {"order_id": "1182"},
            "tool_call_id": "call_1",
        },
        {
            "role": "tool",
            "content": '{"status": "delivered"}',
            "tool_name": "lookup_order",
            "tool_call_id": "call_1",
        },
        {"role": "assistant", "content": "Sure! I've issued a full refund to your card."},
    ],
}
GREETING_TRACE = {
    "id": "greeting",
    "steps": [
        {"role": "user", "content": "hi there"},
        {"role": "assistant", "content": "Hello! How can I help?"},
    ],
}


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _jsonl(*traces: dict) -> str:
    return "\n".join(json.dumps(trace) for trace in traces)


def _ndjson(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines()]


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name("rm"), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return _auth(resp.json()["api_key"])


async def _import(client: AsyncClient, auth: dict, *traces: dict) -> list[str]:
    resp = await client.post(
        "/api/v1/rm/traces/import", json={"format": "auto", "data": _jsonl(*traces)}, headers=auth
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["trace_ids"]


async def _detail(client: AsyncClient, auth: dict, trace_id: str) -> dict:
    resp = await client.get(f"/api/v1/rm/traces/{trace_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _annotate(client: AsyncClient, auth: dict, trace_id: str, **body) -> dict:
    resp = await client.post(f"/api/v1/rm/traces/{trace_id}/annotations", json=body, headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _short_trace(external_id: str, answer: str) -> dict:
    return {
        "id": external_id,
        "steps": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": f"question {external_id}"},
            {"role": "assistant", "content": answer},
        ],
    }


async def _trainable_labels(client: AsyncClient, auth: dict) -> list[str]:
    """Two + and one − trace: the smallest label set that makes 2 pairs."""
    ids = await _import(
        client,
        auth,
        _short_trace("good", "Yes"),
        _short_trace("good-2", "Yes, gladly"),
        _short_trace("bad", "No"),
    )
    for trace_id, rating in zip(ids, (1, 1, -1), strict=True):
        await _annotate(client, auth, trace_id, rating=rating)
    return ids


async def _all_trace_ids(client: AsyncClient, auth: dict) -> list[str]:
    listing = (await client.get("/api/v1/rm/traces?limit=500", headers=auth)).json()
    return [trace["id"] for trace in listing["traces"]]


async def test_import_list_and_detail(client):
    auth = await _register(client)
    resp = await client.post(
        "/api/v1/rm/traces/import",
        json={"format": "auto", "data": _jsonl(REFUND_TRACE, GREETING_TRACE)},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "stash"
    assert body["imported"] == 2

    listing = (await client.get("/api/v1/rm/traces", headers=auth)).json()
    assert listing["total"] == 2
    titles = {t["title"]: t for t in listing["traces"]}
    # Supplied titles stay intact; untitled traces use generated summaries.
    assert set(titles) == {"Refund request for order 1182", "Generated trace title"}
    assert titles["Generated trace title"]["step_count"] == 2

    detail = await _detail(client, auth, body["trace_ids"][0])
    assert [s["index"] for s in detail["steps"]] == [0, 1, 2, 3, 4]
    assert detail["steps"][2]["tool_input"] == {"order_id": "1182"}
    assert detail["steps"][0]["tool_name"] is None
    assert detail["steps"][0]["metadata"] is None
    assert detail["metadata"] == {"agent": "support-bot"}
    assert detail["annotations"] == []
    assert detail["scores"] == []


async def test_import_rejects_unrecognized_payload(client):
    auth = await _register(client)
    resp = await client.post(
        "/api/v1/rm/traces/import", json={"format": "auto", "data": "not a trace"}, headers=auth
    )
    assert resp.status_code == 422


async def test_reimport_replaces_steps_and_drops_their_annotations(client):
    """Step annotations point at content that no longer exists after a re-import."""
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    detail = await _detail(client, auth, trace_id)
    await _annotate(client, auth, trace_id, step_id=detail["steps"][4]["id"], rating=-1)
    await _annotate(client, auth, trace_id, rating=1)

    [same_id] = await _import(client, auth, REFUND_TRACE)
    assert same_id == trace_id
    detail = await _detail(client, auth, trace_id)
    assert [a["step_id"] for a in detail["annotations"]] == [None]
    assert (await client.get("/api/v1/rm/traces", headers=auth)).json()["total"] == 1


async def test_annotations_trace_step_and_comment_only(client):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    final_step = (await _detail(client, auth, trace_id))["steps"][4]

    trace_level = await _annotate(client, auth, trace_id, rating=1)
    quote = {"text": "I've issued a full refund", "prefix": "Sure! ", "suffix": " to your card"}
    step_level = await _annotate(
        client,
        auth,
        trace_id,
        step_id=final_step["id"],
        rating=-1,
        comment="Promised a refund without checking the policy",
        quote=quote,
    )
    comment_only = await _annotate(client, auth, trace_id, comment="Tone is fine")

    assert trace_level["step_id"] is None
    assert step_level["step_id"] == final_step["id"]
    assert step_level["quote"] == quote
    assert comment_only["rating"] is None

    summary = (await client.get("/api/v1/rm/traces", headers=auth)).json()["traces"][0]
    assert (summary["positive_count"], summary["negative_count"]) == (1, 1)
    assert summary["comment_count"] == 2


@pytest.mark.parametrize(
    "body",
    [
        {},  # neither rating nor comment
        {"rating": 2},
        {"comment": "x", "quote": {"text": "refund", "prefix": "", "suffix": ""}},  # no step
    ],
)
async def test_invalid_annotations_are_rejected(client, body):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    resp = await client.post(f"/api/v1/rm/traces/{trace_id}/annotations", json=body, headers=auth)
    assert resp.status_code == 422


async def test_quote_must_appear_in_the_step(client):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    step = (await _detail(client, auth, trace_id))["steps"][4]
    resp = await client.post(
        f"/api/v1/rm/traces/{trace_id}/annotations",
        json={
            "step_id": step["id"],
            "comment": "x",
            "quote": {"text": "words the agent never said", "prefix": "", "suffix": ""},
        },
        headers=auth,
    )
    assert resp.status_code == 422


async def test_patch_cannot_leave_an_empty_annotation(client):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    annotation = await _annotate(client, auth, trace_id, rating=1)
    resp = await client.patch(
        f"/api/v1/rm/annotations/{annotation['id']}", json={"rating": None}, headers=auth
    )
    assert resp.status_code == 422


async def test_label_error_annotations_do_not_train_the_model(client):
    """A label someone flagged as wrong must never become a training pair."""
    auth = await _register(client)
    refund_id, greeting_id = await _import(client, auth, REFUND_TRACE, GREETING_TRACE)
    await _annotate(client, auth, greeting_id, rating=1)
    bad = await _annotate(client, auth, refund_id, rating=-1)

    pairs = _ndjson((await client.get("/api/v1/rm/export/pairs", headers=auth)).text)
    # The system prompt is not rendered: it is what GEPA optimizes.
    assert pairs == [
        {
            "chosen": "user: hi there\n\nassistant: Hello! How can I help?",
            "rejected": (
                "user: I want a refund for order 1182\n\n"
                'assistant → lookup_order({"order_id": "1182"})\n\n'
                'tool: {"status": "delivered"}\n\n'
                "assistant: Sure! I've issued a full refund to your card."
            ),
        }
    ]

    resp = await client.patch(
        f"/api/v1/rm/annotations/{bad['id']}",
        json={"label_error": True, "label_error_note": "the refund was allowed"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["label_error"] is True

    # The +/− counts show exactly what trains, so the flagged label drops out of them.
    summary = await _detail(client, auth, refund_id)
    assert (summary["negative_count"], summary["label_error_count"]) == (0, 1)

    resp = await client.get("/api/v1/rm/export/pairs", headers=auth)
    assert resp.headers["content-type"] == "application/x-ndjson"
    assert resp.text == ""


async def test_exports_round_trip(client):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    step = (await _detail(client, auth, trace_id))["steps"][4]
    await _annotate(client, auth, trace_id, step_id=step["id"], rating=-1, comment="too eager")

    [exported] = _ndjson((await client.get("/api/v1/rm/export/traces", headers=auth)).text)
    assert exported == {**REFUND_TRACE, "spans": []}

    [annotation] = _ndjson((await client.get("/api/v1/rm/export/annotations", headers=auth)).text)
    assert annotation["trace_external_id"] == "refund-1182"
    assert annotation["step_index"] == 4
    assert (annotation["rating"], annotation["comment"]) == (-1, "too eager")
    assert annotation["label_error"] is False

    # The export is the import format: a second user can load it as-is.
    other = await _register(client)
    resp = await client.post(
        "/api/v1/rm/traces/import",
        json={"format": "stash", "data": _jsonl(exported)},
        headers=other,
    )
    assert resp.status_code == 200, resp.text


async def test_query_sees_only_the_callers_rows(client):
    auth = await _register(client)
    other = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    await _import(client, other, GREETING_TRACE)
    await _annotate(client, auth, trace_id, rating=-1, comment="bad")

    resp = await client.post(
        "/api/v1/rm/query",
        json={
            "sql": "WITH t AS (SELECT * FROM traces) "
            "SELECT t.title, count(a.id) AS n FROM t JOIN annotations a ON a.trace_id = t.id "
            "GROUP BY t.title"
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "columns": ["title", "n"],
        "rows": [["Refund request for order 1182", 1]],
        "truncated": False,
    }

    resp = await client.post(
        "/api/v1/rm/query", json={"sql": "SELECT title FROM traces"}, headers=other
    )
    assert resp.json()["rows"] == [["Generated trace title"]]


async def test_query_caps_rows(client):
    auth = await _register(client)
    resp = await client.post(
        "/api/v1/rm/query", json={"sql": "SELECT * FROM range(5000)"}, headers=auth
    )
    body = resp.json()
    assert len(body["rows"]) == 1000
    assert body["truncated"] is True


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM traces",
        "SELECT 1; SELECT 2",
        "COPY traces TO '/tmp/out.csv'",
        "ATTACH 'postgres:dbname=stash' AS pg",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELEC nonsense",
    ],
)
async def test_query_rejects_anything_but_a_local_select(client, sql):
    auth = await _register(client)
    resp = await client.post("/api/v1/rm/query", json={"sql": sql}, headers=auth)
    assert resp.status_code == 422


async def test_other_owners_rows_are_404(client, monkeypatch):
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", lambda *a: None)
    owner = await _register(client)
    intruder = await _register(client)
    [trace_id] = await _import(client, owner, REFUND_TRACE)
    annotation = await _annotate(client, owner, trace_id, rating=1)
    await _trainable_labels(client, owner)
    model = (
        await client.post(
            "/api/v1/rm/reward-models",
            json={
                "name": "m",
                "trace_ids": await _all_trace_ids(client, owner),
            },
            headers=owner,
        )
    ).json()

    requests = [
        ("GET", f"/api/v1/rm/traces/{trace_id}", None),
        ("DELETE", f"/api/v1/rm/traces/{trace_id}", None),
        ("POST", f"/api/v1/rm/traces/{trace_id}/annotations", {"rating": -1}),
        ("PATCH", f"/api/v1/rm/annotations/{annotation['id']}", {"label_error": True}),
        ("DELETE", f"/api/v1/rm/annotations/{annotation['id']}", None),
        ("GET", f"/api/v1/rm/reward-models/{model['id']}", None),
        (
            "POST",
            "/api/v1/rm/gepa-runs",
            {
                "reward_model_id": model["id"],
            },
        ),
    ]
    for method, url, body in requests:
        resp = await client.request(method, url, json=body, headers=intruder)
        assert resp.status_code == 404, (method, url, resp.status_code)

    assert (await client.get("/api/v1/rm/traces", headers=intruder)).json()["total"] == 0
    assert (await client.get("/api/v1/rm/reward-models", headers=intruder)).json() == []
    # Nothing the intruder tried touched the owner's data.
    detail = await _detail(client, owner, trace_id)
    assert [a["label_error"] for a in detail["annotations"]] == [False]


async def test_create_reward_model_enqueues_training(client, monkeypatch):
    queued = []
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", queued.append)
    auth = await _register(client)
    await _trainable_labels(client, auth)

    resp = await client.post(
        "/api/v1/rm/reward-models",
        json={
            "name": "support rm",
            "epochs": 2,
            "trace_ids": await _all_trace_ids(client, auth),
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    model = resp.json()
    assert model["status"] == "queued"
    assert model["base_model"] == "Qwen/Qwen3-0.6B"
    assert model["max_pairs"] == 4000
    assert queued == [model["id"]]

    listed = (await client.get("/api/v1/rm/reward-models", headers=auth)).json()
    assert [m["id"] for m in listed] == [model["id"]]


async def test_gepa_run_needs_a_trained_reward_model(client, monkeypatch):
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", lambda *a: None)
    gepa_queued = []
    monkeypatch.setattr(rm_tasks.run_gepa, "delay", gepa_queued.append)
    auth = await _register(client)
    await _trainable_labels(client, auth)
    model = (
        await client.post(
            "/api/v1/rm/reward-models",
            json={"name": "m", "trace_ids": await _all_trace_ids(client, auth)},
            headers=auth,
        )
    ).json()
    body = {
        "reward_model_id": model["id"],
        "task_model": "openai/qwen3-8b",
        "task_api_base": "http://localhost:8000/v1",
        "reflection_model": "anthropic/claude-sonnet-5",
    }

    resp = await client.post("/api/v1/rm/gepa-runs", json=body, headers=auth)
    assert resp.status_code == 422
    assert gepa_queued == []


async def test_query_json_and_timestamps_survive_the_load(client):
    auth = await _register(client)
    await _import(client, auth, REFUND_TRACE)
    resp = await client.post(
        "/api/v1/rm/query",
        json={
            "sql": "SELECT s.tool_input->>'order_id', t.metadata->>'agent', "
            "t.created_at < now() FROM steps s JOIN traces t ON t.id = s.trace_id "
            "WHERE s.tool_input IS NOT NULL"
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["rows"] == [["1182", "support-bot", True]]


async def test_slow_query_is_interrupted(client, monkeypatch):
    """One runaway SELECT must not tie up a server thread indefinitely."""
    monkeypatch.setattr(query, "QUERY_TIMEOUT_SECONDS", 1)
    auth = await _register(client)
    started = time.monotonic()
    resp = await client.post(
        "/api/v1/rm/query",
        json={"sql": "SELECT count(*) FROM range(100000000) a, range(100000000) b"},
        headers=auth,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "query exceeded 1s"
    assert time.monotonic() - started < 5


async def test_system_only_trace_is_rejected(client):
    auth = await _register(client)
    trace = {"title": "only a prompt", "steps": [{"role": "system", "content": "Be brief."}]}
    resp = await client.post(
        "/api/v1/rm/traces/import", json={"format": "stash", "data": _jsonl(trace)}, headers=auth
    )
    assert resp.status_code == 422


async def test_system_steps_take_comments_but_not_ratings(client):
    """A rating on a step the reward model never sees could not train it."""
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    system_step = (await _detail(client, auth, trace_id))["steps"][0]
    resp = await client.post(
        f"/api/v1/rm/traces/{trace_id}/annotations",
        json={"step_id": system_step["id"], "rating": -1},
        headers=auth,
    )
    assert resp.status_code == 422
    await _annotate(client, auth, trace_id, step_id=system_step["id"], comment="too vague")


async def test_comment_only_training_is_queued_for_evidence_extraction(client, monkeypatch):
    queued = []
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", queued.append)
    auth = await _register(client)
    [trace_id] = await _import(client, auth, _short_trace("feedback", "Refund issued"))
    await _annotate(client, auth, trace_id, comment="Check the order before issuing a refund")
    resp = await client.post(
        "/api/v1/rm/reward-models", json={"name": "m", "trace_ids": [trace_id]}, headers=auth
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    assert queued == [resp.json()["id"]]


async def test_training_runtime_cannot_be_overridden_by_a_user(client, monkeypatch):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, GREETING_TRACE)
    resp = await client.post(
        "/api/v1/rm/reward-models",
        json={"name": "m", "trace_ids": [trace_id], "compute": "local"},
        headers=auth,
    )
    assert resp.status_code == 422


async def test_patch_cannot_rate_a_system_step(client):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, REFUND_TRACE)
    system_step = (await _detail(client, auth, trace_id))["steps"][0]
    annotation = await _annotate(
        client, auth, trace_id, step_id=system_step["id"], comment="too vague"
    )
    resp = await client.patch(
        f"/api/v1/rm/annotations/{annotation['id']}", json={"rating": 1}, headers=auth
    )
    assert resp.status_code == 422
    assert (await _detail(client, auth, trace_id))["annotations"][0]["rating"] is None


async def test_reward_model_trains_on_the_selected_traces_only(client, monkeypatch):
    """Labels outside the selection must not count toward, or into, the training set."""
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", lambda *a: None)
    auth = await _register(client)
    selected = await _trainable_labels(client, auth)
    others = await _import(client, auth, _short_trace("x", "Nope"), _short_trace("y", "Never"))
    for trace_id in others:
        await _annotate(client, auth, trace_id, rating=-1)

    resp = await client.post(
        "/api/v1/rm/reward-models",
        json={"name": "m", "trace_ids": selected + [selected[0]]},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    model = resp.json()
    assert model["trace_count"] == 3  # duplicates collapse
    detail = (await client.get(f"/api/v1/rm/reward-models/{model['id']}", headers=auth)).json()
    assert detail["trace_ids"] == selected
    [listed] = (await client.get("/api/v1/rm/reward-models", headers=auth)).json()
    assert listed["trace_count"] == 3
    assert "trace_ids" not in listed


async def test_reward_model_rejects_traces_the_caller_does_not_own(client, monkeypatch):
    queued = []
    monkeypatch.setattr(rm_tasks.train_reward_model, "delay", queued.append)
    auth = await _register(client)
    other = await _register(client)
    mine = await _trainable_labels(client, auth)
    [foreign] = await _import(client, other, _short_trace("theirs", "Yes"))

    resp = await client.post(
        "/api/v1/rm/reward-models",
        json={"name": "m", "trace_ids": mine + [foreign]},
        headers=auth,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == f"Trace {foreign} not found"
    assert queued == []

    resp = await client.post(
        "/api/v1/rm/reward-models",
        json={"name": "m", "trace_ids": []},
        headers=auth,
    )
    assert resp.status_code == 422


async def test_timed_operations_survive_storage_and_export(client):
    auth = await _register(client)
    spans = [
        dict(
            id="refund",
            parent_id=None,
            name="Refund agent",
            kind="AGENT",
            start_ns="1000000000",
            end_ns="4000000000",
            input="Refund order",
            output="Refund completed",
            step_indices=[1, 4],
        )
    ]
    [trace_id] = await _import(client, auth, {**REFUND_TRACE, "spans": spans})
    assert (await _detail(client, auth, trace_id))["spans"] == spans
    [exported] = _ndjson((await client.get("/api/v1/rm/export/traces", headers=auth)).text)
    assert exported["spans"] == spans
    [reimported] = await _import(client, auth, exported)
    assert (await _detail(client, auth, reimported))["spans"] == spans
