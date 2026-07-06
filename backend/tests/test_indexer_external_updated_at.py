"""Every indexer must map its provider's modified-timestamp into
external_updated_at. That column is the VFS's only truthful mtime — without it
a source's documents show `-` dates and are invisible to `ls -t`/`find -mtime`
(see #713). These tests pin the provider-field → column wiring per indexer.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from backend.integrations.asana import indexer as asana_indexer
from backend.integrations.gong import indexer as gong_indexer
from backend.integrations.granola.indexer import _meeting_time
from backend.integrations.jira import indexer as jira_indexer
from backend.integrations.notion import indexer as notion_indexer

SOURCE = {
    "id": "00000000-0000-0000-0000-000000000001",
    "owner_user_id": "00000000-0000-0000-0000-000000000002",
}


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        pass


class _FakeAsyncClient:
    """Answers every GET with the payload configured per URL substring."""

    def __init__(self, payloads: dict[str, dict]):
        self._payloads = payloads

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, *args, **kwargs):
        for fragment, payload in self._payloads.items():
            if fragment in url:
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected GET {url}")


async def _token(user_id, provider):
    return "tok"


@pytest.mark.asyncio
async def test_jira_indexer_maps_issue_updated(monkeypatch):
    captured: list[dict] = []

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(jira_indexer, "get_valid_token", _token)
    monkeypatch.setattr(
        jira_indexer.httpx,
        "AsyncClient",
        _FakeAsyncClient(
            {
                "/search/jql": {
                    "issues": [
                        {
                            "key": "ENG-1",
                            "fields": {
                                "summary": "Ship it",
                                "updated": "2026-07-01T10:00:00.000-0400",
                            },
                        }
                    ],
                    "isLast": True,
                }
            }
        ),
    )
    monkeypatch.setattr(jira_indexer.source_service, "upsert_index_row", capture_upsert)
    monkeypatch.setattr(jira_indexer.source_service, "remove_missing_documents", _noop)

    await jira_indexer.index_jira({**SOURCE, "external_ref": "cloud-1:ENG"})

    assert captured[0]["external_updated_at"] == datetime(
        2026, 7, 1, 10, 0, tzinfo=timezone(timedelta(hours=-4))
    )


@pytest.mark.asyncio
async def test_asana_indexer_maps_task_modified_at(monkeypatch):
    captured: list[dict] = []

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(asana_indexer, "get_valid_token", _token)
    monkeypatch.setattr(
        asana_indexer.httpx,
        "AsyncClient",
        _FakeAsyncClient(
            {
                "/tasks": {
                    "data": [
                        {"gid": "42", "name": "Do thing", "modified_at": "2026-07-02T08:30:00.000Z"}
                    ]
                }
            }
        ),
    )
    monkeypatch.setattr(asana_indexer.source_service, "upsert_index_row", capture_upsert)
    monkeypatch.setattr(asana_indexer.source_service, "remove_missing_documents", _noop)

    await asana_indexer.index_asana({**SOURCE, "external_ref": "proj-1"})

    assert captured[0]["external_updated_at"] == datetime(2026, 7, 2, 8, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_notion_indexer_maps_last_edited_time(monkeypatch):
    captured: list[dict] = []

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    async def fake_block_tree(client, page_id):
        return ["body"], []

    monkeypatch.setattr(notion_indexer, "get_valid_token", _token)
    monkeypatch.setattr(notion_indexer, "fetch_block_tree", fake_block_tree)
    monkeypatch.setattr(notion_indexer, "_extract_title", lambda meta: "Doc")
    monkeypatch.setattr(
        notion_indexer,
        "_notion_client",
        _FakeAsyncClient({"/pages/": {"last_edited_time": "2026-07-03T12:00:00.000Z"}}),
    )
    monkeypatch.setattr(notion_indexer.source_service, "upsert_content_document", capture_upsert)
    monkeypatch.setattr(notion_indexer.source_service, "remove_missing_documents", _noop)

    await notion_indexer.index_notion(
        {**SOURCE, "external_ref": "0123456789abcdef0123456789abcdef"}
    )

    assert captured[0]["external_updated_at"] == datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_gong_indexer_maps_call_started(monkeypatch):
    captured: list[dict] = []

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    async def gong_token(user_id, provider):
        return '{"access_token": "tok", "api_base_url": "https://api.gong.io"}'

    async def call_meta(client, from_dt, to_dt):
        return {"c1": {"id": "c1", "workspaceId": "W1", "started": "2026-06-15T14:00:00Z"}}

    async def transcripts(client, from_dt, to_dt):
        return {"c1": []}

    monkeypatch.setattr(gong_indexer, "get_valid_token", gong_token)
    monkeypatch.setattr(gong_indexer, "_fetch_call_meta", call_meta)
    monkeypatch.setattr(gong_indexer, "_fetch_transcripts", transcripts)
    monkeypatch.setattr(gong_indexer.httpx, "AsyncClient", _FakeAsyncClient({}))
    monkeypatch.setattr(gong_indexer.source_service, "upsert_content_document", capture_upsert)
    monkeypatch.setattr(gong_indexer.source_service, "remove_missing_documents", _noop)
    monkeypatch.setattr(gong_indexer.source_service, "purge_disallowed_copied_documents", _noop)

    await gong_indexer.index_gong({**SOURCE, "settings": {"allowed_workspace_ids": ["W1"]}})

    assert captured[0]["external_updated_at"] == datetime(2026, 6, 15, 14, 0, tzinfo=UTC)


def test_granola_meeting_time_parses_iso_and_tolerates_free_text():
    assert _meeting_time({"date": "2026-07-04T09:00:00Z"}) == datetime(2026, 7, 4, 9, 0, tzinfo=UTC)
    # Granola's MCP tool returns free-form text; an unparseable date must yield
    # no timestamp (rendered as `-`), never a crashed sync or a fabricated date.
    assert _meeting_time({"date": "last Tuesday morning"}) is None
    assert _meeting_time({}) is None


async def _noop(*args, **kwargs):
    return 0
