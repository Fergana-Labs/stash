from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.integrations.github import indexer as github_indexer
from backend.integrations.gmail import indexer as gmail_indexer
from backend.integrations.gong import indexer as gong_indexer
from backend.integrations.google import indexer as google_indexer
from backend.integrations.granola import client as granola_client
from backend.integrations.granola import indexer as granola_indexer
from backend.integrations.jira import indexer as jira_indexer


class _JsonResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _TextBlock:
    type = "text"
    text = "token=secret-token customer transcript for Webflow"


class _ToolErrorResult:
    isError = True
    structuredContent = None
    content = [_TextBlock()]


class _ToolErrorSession:
    async def call_tool(self, name, arguments):
        return _ToolErrorResult()


def _source(external_ref: str) -> dict:
    return {
        "id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "owner_user_id": str(uuid4()),
        "external_ref": external_ref,
    }


def _capture_info(logger, monkeypatch):
    captured_logs: list[tuple[str, tuple, dict]] = []

    def capture(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(logger, "info", capture)
    return captured_logs


async def _token(user_id, provider=None):
    return "provider-token"


async def _noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call_tool",
    [granola_client.call_tool_data, granola_client.call_tool_json],
)
async def test_granola_tool_errors_exclude_provider_output_and_tool_name(call_tool):
    with pytest.raises(RuntimeError) as exc_info:
        await call_tool(
            _ToolErrorSession(),
            "webflow_private_get_meeting_transcript",
            {"meeting_id": "meeting-webflow-secret"},
        )

    message = str(exc_info.value)
    assert message == "Granola tool failed"
    assert "webflow_private_get_meeting_transcript" not in message
    assert "meeting-webflow-secret" not in message
    assert "secret-token" not in message
    assert "customer transcript" not in message
    assert "Webflow" not in message


@pytest.mark.asyncio
async def test_github_index_success_logs_internal_source_id_only(monkeypatch):
    source = _source("Webflow/private-roadmap")
    captured_logs = _capture_info(github_indexer.logger, monkeypatch)

    async def crawl_archive(archive_url, headers, on_text_file):
        await on_text_file("webflow/secret.md", "customer transcript")
        return ["webflow/secret.md"]

    monkeypatch.setattr(github_indexer, "get_valid_token", _token)
    monkeypatch.setattr(
        github_indexer,
        "resolve_archive_url",
        lambda *args, **kwargs: SimpleNamespace(archive_url="archive-url", headers={}),
    )
    monkeypatch.setattr(github_indexer, "_crawl_archive", crawl_archive)
    monkeypatch.setattr(github_indexer.source_service, "upsert_content_document", _noop)
    monkeypatch.setattr(github_indexer.source_service, "remove_missing_documents", _noop)

    await github_indexer.index_github_repo(source)

    assert captured_logs == [
        (
            "github source %s: indexed %d file(s)",
            (UUID(source["id"]), 1),
            {},
        )
    ]
    assert "Webflow/private-roadmap" not in str(captured_logs)
    assert "webflow/secret.md" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_google_drive_index_success_logs_internal_source_id_only(monkeypatch):
    source = _source("drive-root-secret")
    captured_logs = _capture_info(google_indexer.logger, monkeypatch)

    class DriveClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def list_files(client, q):
        return [
            {
                "id": "drive-file-secret",
                "name": "Webflow board plan",
                "mimeType": "text/plain",
            }
        ]

    monkeypatch.setattr(google_indexer, "get_valid_token", _token)
    monkeypatch.setattr(google_indexer.httpx, "AsyncClient", lambda *args, **kwargs: DriveClient())
    monkeypatch.setattr(google_indexer, "_list", list_files)
    monkeypatch.setattr(google_indexer.source_service, "upsert_index_row", _noop)
    monkeypatch.setattr(google_indexer.source_service, "remove_missing_documents", _noop)

    await google_indexer.index_google_drive(source)

    assert captured_logs == [
        (
            "google drive source %s: indexed %d file(s)",
            (UUID(source["id"]), 1),
            {},
        )
    ]
    assert "drive-root-secret" not in str(captured_logs)
    assert "drive-file-secret" not in str(captured_logs)
    assert "Webflow board plan" not in str(captured_logs)


@pytest.mark.asyncio
async def test_gmail_index_success_logs_internal_source_id_only(monkeypatch):
    """Runs index_gmail end to end (with provider calls faked) so the sync
    path — including the remove_missing_documents cleanup call — is exercised
    by at least one test, and the success log stays free of message content."""
    source = {**_source("account-webflow-secret@example.com"), "external_ref": "gmail-account-id"}
    captured_logs = _capture_info(gmail_indexer.logger, monkeypatch)

    class GmailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def gmail_token(user_id, provider, external_ref):
        return "provider-token"

    async def list_refs(client, query, limit):
        return [{"id": "msg-webflow-secret"}]

    async def get_metadata(client, message_id):
        return {
            "id": message_id,
            "payload": {"headers": [{"name": "Subject", "value": "Confidential launch plan"}]},
        }

    monkeypatch.setattr(gmail_indexer, "get_valid_token", gmail_token)
    monkeypatch.setattr(gmail_indexer.httpx, "AsyncClient", lambda *args, **kwargs: GmailClient())
    monkeypatch.setattr(gmail_indexer, "_list_message_refs", list_refs)
    monkeypatch.setattr(gmail_indexer, "_get_message_metadata", get_metadata)
    monkeypatch.setattr(gmail_indexer.source_service, "upsert_index_row", _noop)
    monkeypatch.setattr(gmail_indexer.source_service, "remove_missing_documents", _noop)

    await gmail_indexer.index_gmail(source)

    assert captured_logs == [
        (
            "gmail source %s: indexed %d message(s)",
            (UUID(source["id"]), 1),
            {},
        )
    ]
    assert "msg-webflow-secret" not in str(captured_logs)
    assert "Confidential launch plan" not in str(captured_logs)


@pytest.mark.asyncio
async def test_jira_index_success_logs_internal_source_id_only(monkeypatch):
    source = _source("cloud-secret:WEBFLOW")
    captured_logs = _capture_info(jira_indexer.logger, monkeypatch)

    class JiraClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params):
            return _JsonResponse(
                {
                    "issues": [
                        {
                            "key": "WEBFLOW-1",
                            "fields": {"summary": "Confidential launch plan"},
                        }
                    ],
                    "isLast": True,
                }
            )

    monkeypatch.setattr(jira_indexer, "get_valid_token", _token)
    monkeypatch.setattr(jira_indexer.httpx, "AsyncClient", lambda *args, **kwargs: JiraClient())
    monkeypatch.setattr(jira_indexer.source_service, "upsert_index_row", _noop)
    monkeypatch.setattr(jira_indexer.source_service, "remove_missing_documents", _noop)

    await jira_indexer.index_jira(source)

    assert captured_logs == [
        (
            "jira source %s: indexed %d issue(s)",
            (UUID(source["id"]), 1),
            {},
        )
    ]
    assert "cloud-secret" not in str(captured_logs)
    assert "WEBFLOW" not in str(captured_logs)
    assert "WEBFLOW-1" not in str(captured_logs)
    assert "Confidential launch plan" not in str(captured_logs)


@pytest.mark.asyncio
async def test_gong_index_success_logs_internal_source_id_only(monkeypatch):
    source = {
        **_source("calls"),
        "source_type": "gong_calls",
        "settings": {"allowed_workspace_ids": ["gong-workspace-secret"]},
    }
    captured_logs = _capture_info(gong_indexer.logger, monkeypatch)

    async def call_meta(client, from_dt, to_dt):
        return {
            "call-webflow-secret": {
                "id": "call-webflow-secret",
                "workspaceId": "gong-workspace-secret",
                "title": "Webflow acquisition call",
            }
        }

    async def transcripts(client, from_dt, to_dt):
        return {
            "call-webflow-secret": [
                {"speakerId": "1", "sentences": [{"text": "customer transcript"}]}
            ]
        }

    class GongClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def gong_token(user_id, provider):
        return '{"access_key":"key","access_key_secret":"secret"}'

    monkeypatch.setattr(gong_indexer, "get_valid_token", gong_token)
    monkeypatch.setattr(gong_indexer.httpx, "AsyncClient", lambda *args, **kwargs: GongClient())
    monkeypatch.setattr(gong_indexer, "_fetch_call_meta", call_meta)
    monkeypatch.setattr(gong_indexer, "_fetch_transcripts", transcripts)
    monkeypatch.setattr(gong_indexer.source_service, "purge_disallowed_copied_documents", _noop)
    monkeypatch.setattr(gong_indexer.source_service, "upsert_content_document", _noop)
    monkeypatch.setattr(gong_indexer.source_service, "remove_missing_documents", _noop)

    await gong_indexer.index_gong(source)

    assert captured_logs == [
        (
            "gong source %s: indexed %d call(s)",
            (UUID(source["id"]), 1),
            {},
        )
    ]
    assert "gong-workspace-secret" not in str(captured_logs)
    assert "call-webflow-secret" not in str(captured_logs)
    assert "Webflow acquisition call" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


@pytest.mark.asyncio
async def test_granola_index_logs_only_source_metadata(monkeypatch):
    source = _source("granola")
    captured_logs = _capture_info(granola_indexer.logger, monkeypatch)

    class GranolaSession:
        async def list_tools(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(name="webflow_private_list_meetings"),
                    SimpleNamespace(name="webflow_private_get_transcript"),
                ]
            )

    @asynccontextmanager
    async def granola_session(access_token):
        yield GranolaSession()

    async def call_tool_data(session, name, arguments):
        if "list" in name:
            return [
                {
                    "id": "meeting-webflow-secret",
                    "title": "Webflow board meeting",
                    "participants": "ceo@webflow.com",
                }
            ]
        raise RuntimeError("token=secret-token customer transcript")

    monkeypatch.setattr(granola_indexer, "get_valid_access_token", _token)
    monkeypatch.setattr(granola_indexer, "granola_session", granola_session)
    monkeypatch.setattr(granola_indexer, "call_tool_data", call_tool_data)
    monkeypatch.setattr(granola_indexer.source_service, "upsert_content_document", _noop)
    monkeypatch.setattr(granola_indexer.source_service, "remove_missing_documents", _noop)

    await granola_indexer.index_granola(source)

    assert captured_logs == [
        (
            "granola source %s: discovered %d MCP tool(s)",
            (UUID(source["id"]), 2),
            {},
        ),
        (
            "granola source %s: listed %d meeting(s)",
            (UUID(source["id"]), 1),
            {},
        ),
        (
            "granola transcript fetch failed source=%s exception_type=%s",
            (UUID(source["id"]), "RuntimeError"),
            {},
        ),
        (
            "granola source %s: indexed %d meeting(s)",
            (UUID(source["id"]), 1),
            {},
        ),
    ]
    assert "webflow_private" not in str(captured_logs)
    assert "meeting-webflow-secret" not in str(captured_logs)
    assert "Webflow board meeting" not in str(captured_logs)
    assert "ceo@webflow.com" not in str(captured_logs)
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
