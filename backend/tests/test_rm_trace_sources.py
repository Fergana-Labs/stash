"""Stable import origins, owner-scoped aliases, and compatibility with old traces."""

import json
from uuid import UUID

import pytest

from backend.services.rm.trace_sources import default_name, source_id

from .test_rm_api import GREETING_TRACE, _detail, _import, _register
from .test_rm_otel import _chain_span, _llm_span, _payload, _send_json, _traces

pytestmark = pytest.mark.usefixtures("rm_title_generator")


async def test_source_name_applies_to_existing_and_future_traces_without_invalidating_scores(
    client, pool
):
    auth = await _register(client)
    [trace_id] = await _import(client, auth, {**GREETING_TRACE, "metadata": {"agent": "codex"}})
    original = await _detail(client, auth, trace_id)
    assert original["source_id"] == "codex"
    assert original["source_name"].endswith("’s Codex")
    before = await pool.fetchrow(
        "SELECT updated_at, metadata FROM rm_traces WHERE id=$1", UUID(trace_id)
    )
    response = await client.put(
        "/api/v1/rm/trace-sources",
        headers=auth,
        json={"source_id": "codex", "name": " Henry’s Codex "},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"source_id": "codex", "source_name": "Henry’s Codex"}
    assert (await _detail(client, auth, trace_id))["source_name"] == "Henry’s Codex"
    after = await pool.fetchrow(
        "SELECT updated_at, metadata FROM rm_traces WHERE id=$1", UUID(trace_id)
    )
    assert after == before  # No trace revision change or re-scoring trigger.

    await _import(client, auth, {**GREETING_TRACE, "id": "future", "metadata": {"agent": "codex"}})
    listing = (await client.get("/api/v1/rm/traces", headers=auth)).json()["traces"]
    assert len(listing) == 2
    assert {trace["source_name"] for trace in listing} == {"Henry’s Codex"}
    assert {trace["source_owner_id"] for trace in listing} == {original["source_owner_id"]}


async def test_source_aliases_are_scoped_to_authenticated_owner(client):
    first, second = await _register(client), await _register(client)
    data = {**GREETING_TRACE, "metadata": {"source_id": "parts-agent"}}
    [first_id] = await _import(client, first, data)
    [second_id] = await _import(client, second, data)
    await client.put(
        "/api/v1/rm/trace-sources",
        headers=first,
        json={"source_id": "parts-agent", "name": "Heavi"},
    )
    assert (await _detail(client, first, first_id))["source_name"] == "Heavi"
    assert (await _detail(client, second, second_id))["source_name"] == "parts-agent"
    await client.put(
        "/api/v1/rm/trace-sources",
        headers=second,
        json={"source_id": "parts-agent", "name": "Another agent"},
    )
    assert (await _detail(client, first, first_id))["source_name"] == "Heavi"
    assert (await _detail(client, second, second_id))["source_name"] == "Another agent"


async def test_explicit_import_source_overrides_metadata_and_survives_omitted_source_on_reimport(
    client,
):
    auth = await _register(client)
    data = {**GREETING_TRACE, "metadata": {"agent": "some-agent", "source_id": "recorded-source"}}
    response = await client.post(
        "/api/v1/rm/traces/import",
        headers=auth,
        json={"format": "auto", "data": json.dumps(data), "source_id": " heavi "},
    )
    assert response.status_code == 200, response.text
    [trace_id] = response.json()["trace_ids"]
    assert (await _detail(client, auth, trace_id))["source_id"] == "heavi"
    assert await _import(client, auth, GREETING_TRACE) == [trace_id]
    assert (await _detail(client, auth, trace_id))["source_id"] == "heavi"
    await _import(client, auth, data)
    assert (await _detail(client, auth, trace_id))["source_id"] == "recorded-source"


async def test_otel_source_header_survives_later_batches(client):
    auth = await _register(client)
    response = await _send_json(
        client, {**auth, "X-Stash-Trace-Source": "heavi"}, _payload(_chain_span(), _llm_span())
    )
    assert response.status_code == 200, response.text
    [trace] = await _traces(client, auth)
    assert trace["source_id"] == "heavi"
    response = await _send_json(client, auth, _payload(_llm_span(answer="Updated answer")))
    assert response.status_code == 200, response.text
    [updated] = await _traces(client, auth)
    assert updated["id"] == trace["id"]
    assert updated["source_id"] == "heavi"


async def test_empty_and_oversized_source_ids_and_names_are_rejected(client):
    auth = await _register(client)
    for invalid in ("   ", "a" * 201):
        response = await client.post(
            "/api/v1/rm/traces/import",
            headers=auth,
            json={"format": "auto", "data": json.dumps(GREETING_TRACE), "source_id": invalid},
        )
        assert response.status_code == 422
        response = await _send_json(
            client, {**auth, "X-Stash-Trace-Source": invalid}, _payload(_llm_span())
        )
        assert response.status_code == 422
    for invalid in (" ", "a" * 121):
        response = await client.put(
            "/api/v1/rm/trace-sources", headers=auth, json={"source_id": "heavi", "name": invalid}
        )
        assert response.status_code == 422
    assert await _traces(client, auth) == []


def test_legacy_metadata_fallbacks():
    assert source_id({"source_id": "explicit", "agent": "codex"}, "stash") == "explicit"
    assert source_id({"agent": "codex", "source": "other"}, "stash") == "codex"
    assert source_id({"source": "heavi"}, "stash") == "heavi"
    assert source_id({"source_id": 123, "agent": " "}, "otel") == "otel"
    assert default_name("codex", "Henry") == "Henry’s Codex"
    assert default_name("claude_code", "Henry") == "Henry’s Claude Code"
    assert default_name("heavi") == "heavi"
