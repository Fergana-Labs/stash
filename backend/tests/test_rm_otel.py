"""Live OTLP/HTTP receiver: agents export spans in batches; Stash keeps each trace current."""

import base64
import copy
import gzip
import json

import pytest
from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from .test_rm_api import _annotate, _detail, _register

pytestmark = pytest.mark.usefixtures("rm_title_generator")

URL = "/api/v1/rm/otel/v1/traces"
TRACE_ID = "5b8efff798038103d269b633813fc60c"


def _attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": value}}


def _chain_span(trace_id: str = TRACE_ID) -> dict:
    """The agent's root span: no LLM messages of its own."""
    return {
        "traceId": trace_id,
        "spanId": "aaaaaaaaaaaaaaaa",
        "name": "agent run",
        "startTimeUnixNano": "1790000000000000000",
        "endTimeUnixNano": "1790000009000000000",
        "attributes": [_attr("openinference.span.kind", "CHAIN")],
    }


def _llm_span(trace_id: str = TRACE_ID, answer: str = "Your order shipped yesterday.") -> dict:
    """An OpenInference LLM span, as openinference-instrumentation-anthropic emits it."""
    return {
        "traceId": trace_id,
        "spanId": "bbbbbbbbbbbbbbbb",
        "parentSpanId": "aaaaaaaaaaaaaaaa",
        "name": "Messages",
        "startTimeUnixNano": "1790000001000000000",
        "endTimeUnixNano": "1790000002000000000",
        "attributes": [
            _attr("openinference.span.kind", "LLM"),
            _attr("llm.input_messages.0.message.role", "system"),
            _attr("llm.input_messages.0.message.content", "You are a support agent."),
            _attr("llm.input_messages.1.message.role", "user"),
            _attr("llm.input_messages.1.message.content", "Where is order 1182?"),
            _attr("llm.output_messages.0.message.role", "assistant"),
            _attr("llm.output_messages.0.message.content", answer),
        ],
    }


def _payload(*spans: dict) -> dict:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [_attr("service.name", "support-bot")]},
                "scopeSpans": [{"scope": {"name": "openinference"}, "spans": list(spans)}],
            }
        ]
    }


def _protobuf(payload: dict) -> bytes:
    """The same export as protobuf; protobuf's JSON mapping wants base64 ids, not hex."""
    payload = copy.deepcopy(payload)
    for resource_spans in payload["resourceSpans"]:
        for scope_spans in resource_spans["scopeSpans"]:
            for span in scope_spans["spans"]:
                for key in ("traceId", "spanId", "parentSpanId"):
                    if key in span:
                        span[key] = base64.b64encode(bytes.fromhex(span[key])).decode()
    return ParseDict(payload, ExportTraceServiceRequest()).SerializeToString()


async def _send_json(client, auth: dict, payload: dict):
    return await client.post(
        URL, content=json.dumps(payload), headers={**auth, "Content-Type": "application/json"}
    )


async def _traces(client, auth: dict) -> list[dict]:
    return (await client.get("/api/v1/rm/traces", headers=auth)).json()["traces"]


async def test_json_export_becomes_a_trace(client):
    auth = await _register(client)
    resp = await _send_json(client, auth, _payload(_chain_span(), _llm_span()))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {}

    [summary] = await _traces(client, auth)
    assert summary["external_id"] == TRACE_ID
    assert summary["source_format"] == "otel"
    assert summary["title"] == "Generated trace title"
    steps = (await _detail(client, auth, summary["id"]))["steps"]
    assert [(s["role"], s["content"]) for s in steps] == [
        ("system", "You are a support agent."),
        ("user", "Where is order 1182?"),
        ("assistant", "Your order shipped yesterday."),
    ]


async def test_gzipped_protobuf_export_becomes_a_trace(client):
    """The Python SDK's default: protobuf, optionally gzip-compressed."""
    auth = await _register(client)
    resp = await client.post(
        URL,
        content=gzip.compress(_protobuf(_payload(_chain_span(), _llm_span()))),
        headers={**auth, "Content-Type": "application/x-protobuf", "Content-Encoding": "gzip"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/x-protobuf"
    assert ExportTraceServiceResponse.FromString(resp.content) == ExportTraceServiceResponse()

    [summary] = await _traces(client, auth)
    # Ids arrive as protobuf bytes and are stored as the hex OTLP/JSON uses.
    assert summary["external_id"] == TRACE_ID
    assert summary["step_count"] == 3


async def test_a_trace_split_across_batches_appears_once_its_llm_span_arrives(client, pool):
    """BatchSpanProcessor may export the root span before the LLM call's span."""
    auth = await _register(client)
    resp = await _send_json(client, auth, _payload(_chain_span()))
    assert resp.status_code == 200, resp.text
    assert await _traces(client, auth) == []
    assert await pool.fetchval("SELECT count(*) FROM rm_otel_spans") == 1

    resp = await _send_json(client, auth, _payload(_llm_span()))
    assert resp.status_code == 200, resp.text
    [summary] = await _traces(client, auth)
    assert summary["step_count"] == 3


async def test_resending_spans_is_idempotent_and_keeps_trace_annotations(client):
    """Exporters retry; a retried batch must not duplicate the trace or lose trace-level labels."""
    auth = await _register(client)
    payload = _payload(_chain_span(), _llm_span())
    await _send_json(client, auth, payload)
    [summary] = await _traces(client, auth)
    await _annotate(client, auth, summary["id"], rating=1)

    resp = await _send_json(client, auth, payload)
    assert resp.status_code == 200, resp.text
    [again] = await _traces(client, auth)
    assert again["id"] == summary["id"]
    assert again["step_count"] == 3
    assert again["positive_count"] == 1


async def test_a_changed_span_replaces_the_trace_steps(client):
    auth = await _register(client)
    await _send_json(client, auth, _payload(_llm_span(answer="first answer")))
    await _send_json(client, auth, _payload(_llm_span(answer="second answer")))
    [summary] = await _traces(client, auth)
    steps = (await _detail(client, auth, summary["id"]))["steps"]
    assert steps[-1]["content"] == "second answer"


async def test_spans_are_private_to_each_owner(client):
    """Two users exporting the same trace id never see or complete each other's traces."""
    alice = await _register(client)
    bob = await _register(client)
    await _send_json(client, alice, _payload(_llm_span()))
    await _send_json(client, bob, _payload(_chain_span()))

    assert [t["external_id"] for t in await _traces(client, alice)] == [TRACE_ID]
    assert await _traces(client, bob) == []


async def test_bad_messages_fail_loudly_and_store_nothing(client, pool):
    auth = await _register(client)
    span = _llm_span()
    span["attributes"][1] = _attr("llm.input_messages.0.message.role", "wizard")
    resp = await _send_json(client, auth, _payload(span))
    assert resp.status_code == 400
    assert "wizard" in resp.json()["detail"]
    assert await pool.fetchval("SELECT count(*) FROM rm_otel_spans") == 0


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/plain"},
        {"Content-Type": "application/json", "Content-Encoding": "br"},
    ],
)
async def test_unsupported_bodies_get_415(client, headers):
    auth = await _register(client)
    resp = await client.post(URL, content=b"{}", headers={**auth, **headers})
    assert resp.status_code == 415


async def test_requires_auth(client):
    resp = await client.post(
        URL, content=json.dumps(_payload(_llm_span())), headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 401


async def test_read_only_keys_cannot_ingest(client):
    """Read keys live in agent sandboxes; ingesting traces needs a full-access key."""
    auth = await _register(client)
    resp = await client.post(
        "/api/v1/users/me/keys", json={"name": "sandbox", "access": "read"}, headers=auth
    )
    read_auth = {"Authorization": f"Bearer {resp.json()['api_key']}"}
    resp = await _send_json(client, read_auth, _payload(_llm_span()))
    assert resp.status_code == 403
    assert await _traces(client, auth) == []
