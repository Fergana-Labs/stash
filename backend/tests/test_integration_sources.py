"""Jira + Asana source unit tests.

Two things worth pinning that don't need a DB or live OAuth:

1. The rendering helpers decide what text the agent actually reads for an issue
   or task — so we assert the human-meaningful fields (status, assignee, body,
   comments) survive into the document.
2. A connected source type is only usable if it's wired into EVERY map at once
   (capability, table, content-vs-index, indexer, sync interval). The
   consistency test fails loudly if a future integration wires only some of
   them — the exact bug that makes a source silently un-syncable.
"""

from backend.integrations.asana.indexer import _render_task
from backend.integrations.jira.indexer import _adf_to_text, _render_issue
from backend.services import source_service
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
    """Every connected (non-native) source type must appear in all of the maps
    that make it usable, and its document table must be classified as either
    copied-content or index-only — never neither."""
    capability_types = set(source_service.SOURCE_CAPABILITY)
    for source_type in capability_types:
        assert source_type in source_service.DEFAULT_SYNC_INTERVAL_S, source_type
        assert source_type in source_service.SOURCE_TABLE, source_type
        assert source_type in source_tasks.INDEXERS, source_type

    # Every document table is exactly one storage strategy.
    for source_type, table in source_service.SOURCE_TABLE.items():
        assert source_type in capability_types, source_type
        # content tables hold the body; index-only tables fetch it lazily — a
        # table that's in neither set would break read_document.
        is_content = table in source_service.CONTENT_TABLES
        is_index_only = source_type in ("google_drive", "notion")
        assert is_content or is_index_only, table


def test_jira_and_asana_are_searchable_content_sources():
    assert source_service.SOURCE_TABLE["jira_project"] == "jira_documents"
    assert source_service.SOURCE_TABLE["asana_project"] == "asana_documents"
    assert "jira_documents" in source_service.CONTENT_TABLES
    assert "asana_documents" in source_service.CONTENT_TABLES
    assert source_service.SOURCE_CAPABILITY["jira_project"] == "searchable"
    assert source_service.SOURCE_CAPABILITY["asana_project"] == "navigable"
