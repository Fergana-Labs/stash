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

import pytest

from backend.integrations.asana.indexer import _render_task
from backend.integrations.gong.indexer import _render_call
from backend.integrations.gong.provider import GongIntegration
from backend.integrations.jira.indexer import _adf_to_text, _render_issue
from backend.integrations.snowflake.client import _assert_read_only, _validate_identifier
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

    # Every document table is exactly one storage strategy.
    for source_type, table in source_service.SOURCE_TABLE.items():
        assert source_type in source_service.SOURCE_CAPABILITY, source_type
        # content tables hold the body; index-only tables fetch it lazily — a
        # table that's in neither set would break read_document.
        is_content = table in source_service.CONTENT_TABLES
        is_index_only = source_type in ("google_drive",)
        assert is_content or is_index_only, table


def test_notion_is_searchable_content_source():
    # Notion moved from index-only to copied-content so it's full-text searchable;
    # Drive is now the only remaining lazy-fetch index-only source.
    assert source_service.SOURCE_TABLE["notion"] == "notion_index"
    assert "notion_index" in source_service.CONTENT_TABLES
    assert source_service.SOURCE_CAPABILITY["notion"] == "navigable"


def test_jira_and_asana_are_searchable_content_sources():
    assert source_service.SOURCE_TABLE["jira_project"] == "jira_documents"
    assert source_service.SOURCE_TABLE["asana_project"] == "asana_documents"
    assert "jira_documents" in source_service.CONTENT_TABLES
    assert "asana_documents" in source_service.CONTENT_TABLES
    assert source_service.SOURCE_CAPABILITY["jira_project"] == "searchable"
    assert source_service.SOURCE_CAPABILITY["asana_project"] == "navigable"


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
    assert source_service.SOURCE_TABLE["gong_calls"] == "gong_documents"
    assert "gong_documents" in source_service.CONTENT_TABLES
    assert source_service.SOURCE_CAPABILITY["gong_calls"] == "searchable"


@pytest.mark.asyncio
async def test_gong_rejects_missing_credentials():
    with pytest.raises(ValueError):
        await GongIntegration().connect_with_credentials({"access_key": "", "access_key_secret": ""})


# --- Snowflake (queryable source) -------------------------------------------


def test_read_only_guard_allows_selects():
    # Allowed leading keywords pass; a trailing semicolon is stripped.
    for sql in ("SELECT 1", "  with x as (select 1) select * from x  ", "SHOW TABLES;", "DESCRIBE TABLE t"):
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
        "",
    ):
        with pytest.raises(ValueError):
            _assert_read_only(sql)


def test_validate_identifier_rejects_injection():
    assert _validate_identifier("DB.SCHEMA.TABLE") == "DB.SCHEMA.TABLE"
    for bad in ("t; drop table u", "t where 1=1", "t--", "t)"):
        with pytest.raises(ValueError):
            _validate_identifier(bad)


def test_snowflake_is_queryable_api_key_source():
    sf = SnowflakeIntegration()
    assert sf.auth_kind == "api_key"
    assert sf.credential_fields[0].name == "account"
    assert source_service.SOURCE_CAPABILITY["snowflake"] == "queryable"
    # Queryable sources intentionally have no document table or indexer.
    assert "snowflake" not in source_service.SOURCE_TABLE
    assert "snowflake" not in source_tasks.INDEXERS


@pytest.mark.asyncio
async def test_snowflake_rejects_incomplete_credentials():
    with pytest.raises(ValueError):
        await SnowflakeIntegration().connect_with_credentials({"account": "a"})  # no user/key


def test_query_source_tool_is_registered_and_in_tool_sets():
    # The catalog and the advertised tool sets must agree, or the agent would
    # be offered a tool that doesn't exist (or vice-versa).
    assert "query_source" in agent_runtime._TOOLS_BY_NAME
    assert "query_source" in prompts.STASH_TOOL_SET
    assert "query_source" in prompts.ASK_TOOL_SET
