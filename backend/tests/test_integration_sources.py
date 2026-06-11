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

from uuid import uuid4

import pytest

from backend.integrations.asana.indexer import _render_task
from backend.integrations.gmail import indexer as gmail_indexer
from backend.integrations.gmail.provider import GmailIntegration
from backend.integrations.gong import indexer as gong_indexer
from backend.integrations.gong.indexer import _render_call
from backend.integrations.gong.provider import GongIntegration
from backend.integrations.jira.indexer import _adf_to_text, _render_issue
from backend.integrations.registry import list_providers
from backend.integrations.snowflake import client as snowflake_client
from backend.integrations.snowflake.client import (
    ROW_CAP,
    _assert_read_only,
    _query_limit,
    _validate_identifier,
)
from backend.integrations.snowflake.provider import SnowflakeIntegration
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
    readable. Queryable sources (Snowflake) are the exception: they run live SQL
    and deliberately have no document table or indexer."""
    for source_type, capability in source_service.SOURCE_CAPABILITY.items():
        if capability == "queryable":
            # No table / indexer; reached via query_source, not list_documents.
            assert source_type not in source_service.SOURCE_TABLE, source_type
            assert source_type not in source_tasks.INDEXERS, source_type
            continue
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
    provider_names = {provider.name for provider in list_providers()}
    assert set(source_service.PROVIDER_SOURCE_TYPES) == provider_names


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


def test_gong_is_api_key_searchable_source():
    gong = GongIntegration()
    assert gong.auth_kind == "api_key"
    assert [f.name for f in gong.credential_fields] == ["access_key", "access_key_secret"]
    assert all(f.secret for f in gong.credential_fields)
    assert source_service.normalize_source_settings(
        "gong_calls",
        {"allowed_workspace_ids": ["W1", " W2 ", "W1"]},
    ) == {"allowed_workspace_ids": ["W1", "W2"]}
    assert source_service.SOURCE_TABLE["gong_calls"] == "gong_documents"
    assert "gong_documents" in source_service.CONTENT_TABLES
    assert source_service.SOURCE_CAPABILITY["gong_calls"] == "searchable"


@pytest.mark.asyncio
async def test_gong_rejects_missing_credentials():
    with pytest.raises(ValueError):
        await GongIntegration().connect_with_credentials(
            {"access_key": "", "access_key_secret": ""}
        )


@pytest.mark.asyncio
async def test_gong_indexer_requires_workspace_allowlist(monkeypatch):
    soft_deleted: list[str] = []

    async def fail_get_valid_token(user_id, provider):
        raise AssertionError("Gong credentials should not be touched without an allowlist")

    async def fake_purge_disallowed_copied_documents(source):
        return 0

    async def fake_remove_missing_documents(table, source_id, present_paths):
        soft_deleted.extend(present_paths)

    monkeypatch.setattr(gong_indexer, "get_valid_token", fail_get_valid_token)
    monkeypatch.setattr(
        gong_indexer.source_service,
        "purge_disallowed_copied_documents",
        fake_purge_disallowed_copied_documents,
    )
    monkeypatch.setattr(
        gong_indexer.source_service,
        "remove_missing_documents",
        fake_remove_missing_documents,
    )

    result = await gong_indexer.index_gong(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "owner_user_id": "00000000-0000-0000-0000-000000000003",
            "source_type": "gong_calls",
            "settings": {},
        }
    )

    assert result is None
    assert soft_deleted == []


@pytest.mark.asyncio
async def test_gong_indexer_filters_to_allowed_workspaces(monkeypatch):
    stored_paths: list[str] = []
    stored_workspace_ids: list[str] = []
    soft_deleted: list[str] = []

    async def fake_get_valid_token(user_id, provider):
        return '{"access_key": "ak", "access_key_secret": "secret"}'

    async def fake_fetch_call_meta(client, from_dt, to_dt):
        return {
            "allowed-call": {"id": "allowed-call", "workspaceId": "W_ALLOWED"},
            "blocked-call": {"id": "blocked-call", "workspaceId": "W_BLOCKED"},
        }

    async def fake_fetch_transcripts(client, from_dt, to_dt):
        return {"allowed-call": [], "blocked-call": []}

    async def fake_upsert_content_document(**kwargs):
        stored_paths.append(kwargs["path"])
        stored_workspace_ids.append(kwargs["extra"]["gong_workspace_id"])

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
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "owner_user_id": "00000000-0000-0000-0000-000000000003",
            "source_type": "gong_calls",
            "settings": {"allowed_workspace_ids": ["W_ALLOWED"]},
        }
    )

    assert stored_paths == ["allowed-call"]
    assert stored_workspace_ids == ["W_ALLOWED"]
    assert soft_deleted == ["allowed-call"]


# --- Snowflake (queryable source) -------------------------------------------


def test_read_only_guard_allows_selects():
    # Allowed leading keywords pass; a trailing semicolon is stripped.
    for sql in (
        "SELECT 1",
        "SHOW TABLES;",
        "DESCRIBE TABLE t",
    ):
        assert _assert_read_only(sql)


def test_read_only_guard_blocks_writes_and_multi_statements():
    for sql in (
        "DELETE FROM t",
        "UPDATE t SET x = 1",
        "INSERT INTO t VALUES (1)",
        "DROP TABLE t",
        "CREATE TABLE t (id int)",
        "GRANT SELECT ON t TO r",
        "SELECT 1; DROP TABLE t",  # piggybacked statement
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "WITH x AS (SELECT 1) DELETE FROM t",
        "",
    ):
        with pytest.raises(ValueError):
            _assert_read_only(sql)


def test_validate_identifier_rejects_injection():
    assert _validate_identifier("DB.SCHEMA.TABLE") == "DB.SCHEMA.TABLE"
    for bad in ("t; drop table u", "t where 1=1", "t--", "t)"):
        with pytest.raises(ValueError) as exc:
            _validate_identifier(bad)
        assert str(exc.value) == "invalid table identifier"
        assert bad not in str(exc.value)


def test_snowflake_query_limit_rejects_non_positive_values():
    assert _query_limit(1) == 1
    assert _query_limit(ROW_CAP + 1) == ROW_CAP
    for bad in (0, -1):
        with pytest.raises(ValueError, match="limit must be at least 1"):
            _query_limit(bad)


def test_snowflake_is_queryable_api_key_source():
    sf = SnowflakeIntegration()
    assert sf.auth_kind == "api_key"
    assert sf.credential_fields[0].name == "account"
    assert source_service.SOURCE_CAPABILITY["snowflake"] == "queryable"
    # Queryable sources intentionally have no document table or indexer.
    assert "snowflake" not in source_service.SOURCE_TABLE
    assert "snowflake" not in source_tasks.INDEXERS


def test_snowflake_offers_pat_token_with_optional_alternatives():
    # PAT (a single token) is the easy auth path; key-pair is the optional
    # alternative. Only account + user are required so the form doesn't force
    # users to fill the optional warehouse/role/database/passphrase.
    fields = {f.name: f for f in SnowflakeIntegration().credential_fields}
    assert fields["token"].optional and fields["token"].secret
    assert fields["private_key"].optional
    assert not fields["account"].optional and not fields["user"].optional
    for opt in ("warehouse", "role", "database", "private_key_passphrase"):
        assert fields[opt].optional, opt


@pytest.mark.asyncio
async def test_snowflake_rejects_incomplete_credentials():
    with pytest.raises(ValueError):
        await SnowflakeIntegration().connect_with_credentials({"account": "a"})  # no user/key
    # account + user but no auth method (token/key/password) is also rejected.
    with pytest.raises(ValueError):
        await SnowflakeIntegration().connect_with_credentials({"account": "a", "user": "u"})


@pytest.mark.asyncio
async def test_snowflake_connection_errors_are_redacted(monkeypatch):
    from backend.integrations.snowflake import provider as snowflake_provider

    async def fail_connection(creds):
        raise RuntimeError(f"account={creds['account']} token={creds['token']}")

    monkeypatch.setattr(snowflake_provider, "test_connection", fail_connection)

    with pytest.raises(ValueError) as exc:
        await SnowflakeIntegration().connect_with_credentials(
            {"account": "acme", "user": "svc", "token": "secret-token"}
        )

    assert str(exc.value) == "Could not connect to Snowflake; check credentials"
    assert "secret-token" not in str(exc.value)


@pytest.mark.asyncio
async def test_snowflake_query_runtime_errors_are_redacted(monkeypatch):
    async def fake_creds(owner_user_id):
        return {"account": "webflow", "user": "svc", "token": "secret-token"}

    def fail_query(creds, sql, limit):
        raise ValueError(f"account={creds['account']} token={creds['token']} sql={sql}")

    monkeypatch.setattr(snowflake_client, "_creds", fake_creds)
    monkeypatch.setattr(snowflake_client, "_run_sync", fail_query)

    with pytest.raises(snowflake_client.SnowflakeQueryError) as exc:
        await snowflake_client.run_query(
            {"owner_user_id": str(uuid4())},
            "SELECT * FROM confidential_customer_data",
            10,
        )

    assert str(exc.value) == "Snowflake query failed"
    assert "secret-token" not in str(exc.value)
    assert "confidential_customer_data" not in str(exc.value)


@pytest.mark.asyncio
async def test_snowflake_metadata_runtime_errors_are_redacted(monkeypatch):
    async def fake_creds(owner_user_id):
        return {"account": "webflow", "user": "svc", "token": "secret-token"}

    def fail_metadata(creds, sql, limit):
        raise ValueError(f"account={creds['account']} token={creds['token']} sql={sql}")

    monkeypatch.setattr(snowflake_client, "_creds", fake_creds)
    monkeypatch.setattr(snowflake_client, "_run_sync", fail_metadata)

    with pytest.raises(snowflake_client.SnowflakeMetadataError) as list_exc:
        await snowflake_client.list_tables({"owner_user_id": str(uuid4())})

    with pytest.raises(snowflake_client.SnowflakeMetadataError) as describe_exc:
        await snowflake_client.describe_table(
            {"owner_user_id": str(uuid4())},
            "DB.SCHEMA.confidential_customer_data",
        )

    assert str(list_exc.value) == "Snowflake metadata fetch failed"
    assert str(describe_exc.value) == "Snowflake metadata fetch failed"
    assert "secret-token" not in str(list_exc.value)
    assert "secret-token" not in str(describe_exc.value)
    assert "confidential_customer_data" not in str(describe_exc.value)


def test_query_source_tool_is_registered_and_in_tool_sets():
    # The catalog and the advertised tool sets must agree, or the agent would
    # be offered a tool that doesn't exist (or vice-versa).
    assert "query_source" in agent_runtime._TOOLS_BY_NAME
    assert "query_source" in prompts.STASH_TOOL_SET
    assert "query_source" in prompts.ASK_TOOL_SET


def test_fetch_history_wiring():
    # Copied, time-windowed sources support on-demand history fetch.
    assert source_service.HISTORY_FETCH_TYPES == {"slack", "gong_calls"}
    # Both are copied-content (the cache) AND now fetchable for older data.
    assert source_service.SOURCE_TABLE["slack"] in source_service.CONTENT_TABLES
    assert source_service.SOURCE_TABLE["gong_calls"] in source_service.CONTENT_TABLES
    assert "fetch_history" in agent_runtime._TOOLS_BY_NAME
    assert "fetch_history" in prompts.STASH_TOOL_SET
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
