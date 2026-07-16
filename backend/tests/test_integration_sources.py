"""Jira + Asana + Gong source unit tests.

Two things worth pinning that don't need a DB or live OAuth:

1. The rendering helpers decide what text the agent actually reads for an issue,
   task, or call — so we assert the human-meaningful fields (status, assignee,
   body, comments, transcript) survive into the document.
2. A connected source type is only usable if it's wired into EVERY map at once
   (capability, table, content-vs-index, indexer, sync interval). The
   consistency test fails loudly if a future integration wires only some of
   them — the exact bug that makes a source silently un-syncable.
"""

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.config import settings
from backend.integrations.asana.indexer import _render_task
from backend.integrations.gmail import indexer as gmail_indexer
from backend.integrations.gmail.provider import GmailIntegration
from backend.integrations.gong import indexer as gong_indexer
from backend.integrations.gong.indexer import _render_call
from backend.integrations.gong.provider import GongIntegration
from backend.integrations.jira.indexer import _adf_to_text, _render_issue
from backend.integrations.linear import provider as linear_provider
from backend.integrations.linear.provider import LinearIntegration
from backend.integrations.registry import list_providers
from backend.services import agent_runtime, prompts, source_service
from backend.tasks import sources as source_tasks


def test_adf_to_text_flattens_blocks():
    adf = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "first line"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "second line"}]},
        ],
    }
    assert _adf_to_text(adf) == "first line\nsecond line"
    assert _adf_to_text(None) == ""


def test_render_issue_includes_meaningful_fields():
    issue = {
        "key": "PROJ-7",
        "fields": {
            "summary": "Login is broken",
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Ada Lovelace"},
            "description": {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "repro steps"}]}
                ],
            },
            "comment": {
                "comments": [
                    {
                        "author": {"displayName": "Alan Turing"},
                        "body": {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "cannot reproduce"}],
                                }
                            ],
                        },
                    }
                ]
            },
        },
    }
    text = _render_issue(issue)
    assert "PROJ-7: Login is broken" in text
    assert "Status: In Progress" in text
    assert "Assignee: Ada Lovelace" in text
    assert "repro steps" in text
    assert "Alan Turing: cannot reproduce" in text


def test_render_issue_handles_unassigned_and_empty():
    text = _render_issue({"key": "PROJ-1", "fields": {"summary": "stub"}})
    assert "Assignee: Unassigned" in text


def test_render_task_includes_status_and_notes():
    task = {
        "name": "Ship the thing",
        "completed": False,
        "assignee": {"name": "Grace Hopper"},
        "due_on": "2026-07-01",
        "notes": "remember the migration",
    }
    text = _render_task(task)
    assert "Ship the thing" in text
    assert "Status: Open" in text
    assert "Assignee: Grace Hopper" in text
    assert "Due: 2026-07-01" in text
    assert "remember the migration" in text


def test_render_task_completed_and_unassigned():
    text = _render_task({"name": "done", "completed": True})
    assert "Status: Completed" in text
    assert "Assignee: Unassigned" in text


def test_connected_source_types_are_fully_wired():
    """Document sources must appear in every map that makes them syncable +
    readable: a document table and a registered indexer."""
    for source_type in source_service.SOURCE_CAPABILITY:
        assert source_type in source_service.SOURCE_TABLE, source_type
        assert source_type in source_tasks.INDEXERS, source_type

    # Every document table is exactly one storage strategy: it either copies
    # content (FTS) or is index-only (lazy read). Index-only sources are either
    # federated-searchable (drive/jira/asana) or not searchable at all.
    for source_type, table in source_service.SOURCE_TABLE.items():
        assert source_type in source_service.SOURCE_CAPABILITY, source_type
        is_content = table in source_service.CONTENT_TABLES
        is_index_only = source_type in source_service.FEDERATED_SEARCH_TYPES
        assert is_content or is_index_only, table


def test_provider_disconnect_cleanup_mapping_covers_registered_providers():
    # Every registered provider must have a disconnect-cleanup mapping. The map
    # may also carry provider-less groupings (instagram: the extension pushes
    # the save list; there is no OAuth integration to disconnect).
    provider_names = {provider.name for provider in list_providers()}
    assert provider_names <= set(source_service.PROVIDER_SOURCE_TYPES)


def test_notion_is_searchable_content_source():
    # Notion copies content (its crawl already renders the text), so it's FTS
    # searchable rather than federated.
    assert source_service.SOURCE_TABLE["notion"] == "notion_index"
    assert "notion_index" in source_service.CONTENT_TABLES
    assert "notion" not in source_service.FEDERATED_SEARCH_TYPES


def test_gmail_jira_asana_drive_are_index_only_federated():
    # Gmail/Jira/Asana/Drive don't copy content — search is federated to the
    # provider's own search API and bodies are fetched lazily on read.
    for st in ("gmail", "jira_project", "asana_project", "google_drive"):
        assert st in source_service.FEDERATED_SEARCH_TYPES, st
        assert source_service.SOURCE_TABLE[st] not in source_service.CONTENT_TABLES, st


def test_jira_project_refs_reject_jql_injection_shapes():
    assert source_service.parse_jira_project_ref("cloud-1:PROJ_1") == ("cloud-1", "PROJ_1")

    for external_ref in (
        "cloud-1",
        "cloud-1:",
        ":PROJ",
        "cloud 1:PROJ",
        'cloud-1:PROJ" OR project IS NOT EMPTY',
        "cloud-1:PROJ-1",
    ):
        with pytest.raises(ValueError):
            source_service.parse_jira_project_ref(external_ref)


def test_gmail_is_readonly_searchable_source():
    gmail = GmailIntegration()
    assert "https://www.googleapis.com/auth/gmail.readonly" in gmail.scopes
    assert "https://www.googleapis.com/auth/gmail.modify" not in gmail.scopes
    assert source_service.SOURCE_CAPABILITY["gmail"] == "searchable"
    assert source_service.SOURCE_TABLE["gmail"] == "gmail_index"
    assert "gmail" in source_tasks.INDEXERS
    assert (
        source_service.source_document_url("gmail", "henry@joinstash.ai", "msg-123")
        == "https://mail.google.com/mail/u/henry%40joinstash.ai/#all/msg-123"
    )


def test_gmail_message_rendering_prefers_plain_text_body():
    import base64

    body = base64.urlsafe_b64encode(b"Your invoice is past due.").decode().rstrip("=")
    message = {
        "id": "msg-1",
        "snippet": "invoice snippet",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Past due invoice"},
                {"name": "From", "value": "billing@example.com"},
                {"name": "To", "value": "henry@example.com"},
                {"name": "Date", "value": "Mon, 08 Jun 2026 12:00:00 -0700"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": body},
                }
            ],
        },
    }

    rendered = gmail_indexer._render_message(message)

    assert "# Past due invoice" in rendered
    assert "From: billing@example.com" in rendered
    assert "Snippet: invoice snippet" in rendered
    assert "Your invoice is past due." in rendered


def test_render_call_labels_speakers_and_keeps_transcript():
    text = _render_call(
        {"title": "Q3 sync", "started": "2026-06-01T10:00:00Z"},
        [
            {"speakerId": "a", "sentences": [{"text": "hello there"}]},
            {"speakerId": "b", "sentences": [{"text": "hi"}, {"text": "good to meet you"}]},
            {"speakerId": "a", "sentences": [{"text": "likewise"}]},
        ],
    )
    assert "# Q3 sync" in text
    assert "Date: 2026-06-01T10:00:00Z" in text
    # Stable per-call speaker numbering: first speaker is 1, second is 2.
    assert "[Speaker 1]: hello there" in text
    assert "[Speaker 2]: hi good to meet you" in text
    assert "[Speaker 1]: likewise" in text


def test_gong_is_oauth_searchable_source():
    gong = GongIntegration()
    assert getattr(gong, "auth_kind", "oauth") == "oauth"
    assert gong.supports_refresh is True
    assert {
        "api:calls:read:basic",
        "api:calls:read:transcript",
        "api:workspaces:read",
    } <= set(gong.scopes)
    assert source_service.normalize_source_settings(
        "gong_calls",
        {"allowed_workspace_ids": ["W1", " W2 ", "W1"]},
    ) == {"allowed_workspace_ids": ["W1", "W2"]}
    assert source_service.SOURCE_TABLE["gong_calls"] == "gong_documents"
    assert "gong_documents" in source_service.CONTENT_TABLES
    assert source_service.SOURCE_CAPABILITY["gong_calls"] == "searchable"


def test_gong_authorize_url_carries_scopes_and_redirect(monkeypatch):
    monkeypatch.setattr(settings, "GONG_OAUTH_CLIENT_ID", "client-1")
    monkeypatch.setattr(settings, "GONG_OAUTH_CLIENT_SECRET", "secret-1")
    monkeypatch.setattr(
        settings,
        "GONG_OAUTH_REDIRECT_URI",
        "https://app.example.com/api/v1/integrations/gong/callback",
    )

    parsed = urlparse(GongIntegration().authorize_url("state-1"))
    assert parsed.netloc == "app.gong.io"
    assert parsed.path == "/oauth2/authorize"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["client-1"]
    assert query["state"] == ["state-1"]
    assert query["response_type"] == ["code"]
    assert "api:calls:read:transcript" in query["scope"][0].split()


@pytest.mark.asyncio
async def test_gong_exchange_refresh_and_fetch_account(monkeypatch):
    from backend.integrations.gong import provider as gong_provider

    monkeypatch.setattr(settings, "GONG_OAUTH_CLIENT_ID", "client-1")
    monkeypatch.setattr(settings, "GONG_OAUTH_CLIENT_SECRET", "secret-1")
    monkeypatch.setattr(settings, "GONG_OAUTH_REDIRECT_URI", "https://app.example.com/callback")

    # The per-customer base URL must be bundled into the stored access token so
    # later calls hit the customer's data-center subdomain, not api.gong.io.
    exchange_client = _FakeClient(
        {
            "access_token": "tok",
            "refresh_token": "refresh",
            "expires_in": 86400,
            "scope": "api:calls:read:basic api:calls:read:transcript",
            "api_base_url_for_customer": "https://company-17.api.gong.io",
        }
    )
    monkeypatch.setattr(gong_provider.httpx, "AsyncClient", exchange_client)
    token = await GongIntegration().exchange_code("code-1")
    bundle = json.loads(token.access_token)
    assert bundle == {"access_token": "tok", "api_base_url": "https://company-17.api.gong.io"}
    assert token.refresh_token == "refresh"
    assert exchange_client.posts[0][1]["grant_type"] == "authorization_code"

    # Gong omits a new refresh token on refresh — the old one must survive.
    refresh_client = _FakeClient(
        {
            "access_token": "tok2",
            "expires_in": 86400,
            "api_base_url_for_customer": "https://company-17.api.gong.io",
        }
    )
    monkeypatch.setattr(gong_provider.httpx, "AsyncClient", refresh_client)
    refreshed = await GongIntegration().refresh("old-refresh")
    assert json.loads(refreshed.access_token)["access_token"] == "tok2"
    assert refreshed.refresh_token == "old-refresh"
    assert refresh_client.posts[0][1]["grant_type"] == "refresh_token"

    account_client = _FakeClient({"workspaces": [{"id": "W1", "name": "Acme"}]})
    monkeypatch.setattr(gong_provider.httpx, "AsyncClient", account_client)
    account = await GongIntegration().fetch_account(refreshed.access_token)
    assert account.email is None
    assert account.display_name == "Acme"


@pytest.mark.asyncio
async def test_gong_indexer_requires_account_allowlist(monkeypatch):
    """An unconfigured allowlist must purge previously indexed (unscoped)
    calls and fail the sync — not report a healthy no-op that leaves them
    searchable."""
    purges: list[str] = []

    async def fail_get_valid_token(user_id, provider):
        raise AssertionError("Gong credentials should not be touched without an allowlist")

    async def fake_purge_disallowed_copied_documents(source):
        purges.append(source["id"])
        return 0

    monkeypatch.setattr(gong_indexer, "get_valid_token", fail_get_valid_token)
    monkeypatch.setattr(
        gong_indexer.source_service,
        "purge_disallowed_copied_documents",
        fake_purge_disallowed_copied_documents,
    )

    with pytest.raises(RuntimeError, match="no allowed gong accounts"):
        await gong_indexer.index_gong(
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "owner_user_id": "00000000-0000-0000-0000-000000000002",
                "source_type": "gong_calls",
                "settings": {},
            }
        )

    assert purges == ["00000000-0000-0000-0000-000000000001"]


@pytest.mark.asyncio
async def test_gong_indexer_filters_to_allowed_accounts(monkeypatch):
    stored_paths: list[str] = []
    stored_account_ids: list[str] = []
    soft_deleted: list[str] = []

    async def fake_get_valid_token(user_id, provider):
        return '{"access_token": "tok", "api_base_url": "https://company-17.api.gong.io"}'

    async def fake_fetch_call_meta(client, from_dt, to_dt):
        return {
            "allowed-call": {"id": "allowed-call", "workspaceId": "W_ALLOWED"},
            "blocked-call": {"id": "blocked-call", "workspaceId": "W_BLOCKED"},
        }

    async def fake_fetch_transcripts(client, from_dt, to_dt):
        return {"allowed-call": [], "blocked-call": []}

    async def fake_upsert_content_document(**kwargs):
        stored_paths.append(kwargs["path"])
        stored_account_ids.append(kwargs["extra"]["gong_account_id"])

    async def fake_remove_missing_documents(table, source_id, present_paths):
        soft_deleted.extend(present_paths)

    async def fake_purge_disallowed_copied_documents(source):
        return 0

    monkeypatch.setattr(gong_indexer, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(gong_indexer, "_fetch_call_meta", fake_fetch_call_meta)
    monkeypatch.setattr(gong_indexer, "_fetch_transcripts", fake_fetch_transcripts)
    monkeypatch.setattr(
        gong_indexer.source_service,
        "purge_disallowed_copied_documents",
        fake_purge_disallowed_copied_documents,
    )
    monkeypatch.setattr(
        gong_indexer.source_service,
        "upsert_content_document",
        fake_upsert_content_document,
    )
    monkeypatch.setattr(
        gong_indexer.source_service,
        "remove_missing_documents",
        fake_remove_missing_documents,
    )

    await gong_indexer.index_gong(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "owner_user_id": "00000000-0000-0000-0000-000000000002",
            "source_type": "gong_calls",
            "settings": {"allowed_workspace_ids": ["W_ALLOWED"]},
        }
    )

    assert stored_paths == ["allowed-call"]
    assert stored_account_ids == ["W_ALLOWED"]
    assert soft_deleted == ["allowed-call"]


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        # Mirror real httpx so error-path tests can't silently pass as 200s.
        # The response carries the status so _scoped_search_error can map it.
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=None,
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient; records requests, returns a canned payload."""

    def __init__(self, payload: dict | list[dict], status_code: int | list[int] = 200):
        self.payloads = payload if isinstance(payload, list) else [payload]
        self.status_codes = status_code if isinstance(status_code, list) else [status_code]
        self._index = 0
        self.requests: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict]] = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def _response(self):
        payload = self.payloads[min(self._index, len(self.payloads) - 1)]
        status_code = self.status_codes[min(self._index, len(self.status_codes) - 1)]
        self._index += 1
        return _FakeResponse(payload, status_code)

    async def get(self, url, params=None, headers=None):
        self.requests.append((url, params or {}))
        return self._response()

    async def post(self, url, data=None, auth=None, headers=None):
        self.posts.append((url, data or {}))
        return self._response()


@pytest.mark.asyncio
async def test_linear_exchange_and_refresh_keep_rotating_refresh_token(monkeypatch):
    """Linear issues 24h access tokens with rotating refresh tokens (since its
    2026-04-01 migration). Dropping the refresh token kills the connection
    after a day — exactly the bug this pins against."""
    monkeypatch.setattr(settings, "LINEAR_OAUTH_CLIENT_ID", "client-1")
    monkeypatch.setattr(settings, "LINEAR_OAUTH_CLIENT_SECRET", "secret-1")
    monkeypatch.setattr(settings, "LINEAR_OAUTH_REDIRECT_URI", "https://app.example.com/callback")

    assert LinearIntegration().supports_refresh is True

    exchange_client = _FakeClient(
        {
            "access_token": "tok",
            "refresh_token": "refresh-1",
            "expires_in": 86399,
            "scope": "read",
        }
    )
    monkeypatch.setattr(linear_provider.httpx, "AsyncClient", exchange_client)
    token = await LinearIntegration().exchange_code("code-1")
    assert token.access_token == "tok"
    assert token.refresh_token == "refresh-1"
    assert token.expires_at is not None
    assert token.scopes == ["read"]
    assert exchange_client.posts[0][1]["grant_type"] == "authorization_code"

    refresh_client = _FakeClient(
        {
            "access_token": "tok-2",
            "refresh_token": "refresh-2",
            "expires_in": 86399,
            "scope": "read",
        }
    )
    monkeypatch.setattr(linear_provider.httpx, "AsyncClient", refresh_client)
    refreshed = await LinearIntegration().refresh("refresh-1")
    assert refreshed.access_token == "tok-2"
    assert refreshed.refresh_token == "refresh-2"
    assert refresh_client.posts[0][1]["grant_type"] == "refresh_token"
    assert refresh_client.posts[0][1]["refresh_token"] == "refresh-1"


def test_fetch_history_wiring():
    # Copied, time-windowed sources support on-demand history fetch.
    assert source_service.HISTORY_FETCH_TYPES == {"slack", "gong_calls"}
    # Both are copied-content (the cache) AND now fetchable for older data.
    assert source_service.SOURCE_TABLE["slack"] in source_service.CONTENT_TABLES
    assert source_service.SOURCE_TABLE["gong_calls"] in source_service.CONTENT_TABLES
    assert "fetch_history" in agent_runtime._TOOLS_BY_NAME
    assert "fetch_history" in prompts.ASK_TOOL_SET


def test_parse_dt_accepts_iso_dates():
    assert source_service._parse_dt("2026-01-01").year == 2026
    assert source_service._parse_dt("2026-01-01T08:00:00Z").hour == 8
    assert source_service._parse_dt(None) is None


def test_granola_parses_xml_meeting_blob():
    # Granola's list_meetings returns an XML-ish text blob, not JSON. The
    # participant email contains raw <>, so it isn't valid XML — regex-parsed.
    from backend.integrations.granola.indexer import _parse_meetings_text, _render_meeting

    blob = (
        '<meetings_data count="1">'
        '<meeting id="abc-123" title="Standup" date="Jun 5, 2026">'
        "<known_participants> Sam <sam@x.com> </known_participants>"
        "</meeting></meetings_data>"
    )
    meetings = _parse_meetings_text(blob)
    assert len(meetings) == 1
    assert meetings[0]["id"] == "abc-123"
    assert meetings[0]["title"] == "Standup"
    assert "sam@x.com" in meetings[0]["participants"]  # email preserved
    text = _render_meeting(meetings[0], "we shipped the thing")
    assert "# Standup" in text and "we shipped the thing" in text
