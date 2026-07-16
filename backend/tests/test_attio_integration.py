from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import pytest

from backend.integrations.attio import indexer
from backend.integrations.attio.provider import AttioIntegration


def _async(value):
    async def result(*args, **kwargs):
        return value

    return result


def test_authorize_url_carries_read_scopes_and_state(monkeypatch):
    provider = AttioIntegration()
    monkeypatch.setattr(provider, "_client_id", lambda: "client_abc")
    monkeypatch.setattr(provider, "_redirect_uri", lambda: "https://app.example.com/cb")

    url = provider.authorize_url("state_xyz")
    params = {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}

    assert params["client_id"] == "client_abc"
    assert params["response_type"] == "code"
    assert params["state"] == "state_xyz"
    assert params["scope"] == "meeting:read call_recording:read"


def test_render_call_numbers_speakers_stably():
    rendered = indexer._render_call(
        "HeaviStash Sync",
        "2026-07-01T10:00:00Z",
        [
            {"speech": "Hello there", "speaker": {"name": "Alice"}},
            {"speech": "Hi", "speaker": {"name": "Bob"}},
            {"speech": "  ", "speaker": {"name": "Alice"}},
            {"speech": "Back to you", "speaker": {"name": "Alice"}},
        ],
    )
    assert rendered == (
        "# HeaviStash Sync\n"
        "Date: 2026-07-01T10:00:00Z\n"
        "\n"
        "[Speaker 1]: Hello there\n"
        "[Speaker 2]: Hi\n"
        "[Speaker 1]: Back to you"
    )


@pytest.mark.asyncio
async def test_index_attio_walks_meetings_recordings_and_transcripts(monkeypatch):
    responses = {
        "/v2/meetings": {
            "data": [{"id": {"meeting_id": "m1"}, "title": "HeaviStash Sync"}],
            "pagination": {"next_cursor": None},
        },
        "/v2/meetings/m1/call_recordings": {
            "data": [{"id": {"call_recording_id": "r1"}, "created_at": "2026-07-01T10:00:00Z"}],
            "pagination": {"next_cursor": None},
        },
        "/v2/meetings/m1/call_recordings/r1/transcript": {
            "data": {"transcript": [{"speech": "Hello", "speaker": {"name": "Alice"}}]},
            "pagination": {"next_cursor": None},
        },
    }

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        async def get(self, url, params=None):
            return FakeResponse(responses[url])

    @asynccontextmanager
    async def fake_async_client(*args, **kwargs):
        assert kwargs["headers"] == {"Authorization": "Bearer access_token"}
        yield FakeClient()

    captured: list[dict] = []
    removed: dict = {}

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    async def capture_remove(table, source_id, present_paths):
        removed["present"] = present_paths

    monkeypatch.setattr(indexer, "get_valid_token", _async("access_token"))
    monkeypatch.setattr(indexer.httpx, "AsyncClient", fake_async_client)
    monkeypatch.setattr(indexer.source_service, "upsert_content_document", capture_upsert)
    monkeypatch.setattr(indexer.source_service, "remove_missing_documents", capture_remove)

    await indexer.index_attio(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "owner_user_id": "00000000-0000-0000-0000-000000000002",
        }
    )

    assert len(captured) == 1
    doc = captured[0]
    assert doc["table"] == "attio_documents"
    assert doc["external_ref"] == "r1"
    assert doc["path"] == "r1"
    assert doc["kind"] == "call"
    assert "[Speaker 1]: Hello" in doc["content"]
    assert removed["present"] == ["r1"]
