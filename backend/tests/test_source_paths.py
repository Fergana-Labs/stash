"""Source index paths ARE the VFS: documents list in ORDER BY path, and the
path segments become the folder tree. These tests pin each indexer's path
scheme so a source reads like a sensible filesystem — date folders for
mailboxes and meetings, team/section folders for trackers, numeric issue
order — instead of a flat pile of opaque provider ids (see the VFS audit).
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.integrations.asana.indexer import _task_path
from backend.integrations.gmail.indexer import _message_path
from backend.integrations.granola import indexer as granola_indexer
from backend.integrations.granola.indexer import _meeting_path
from backend.integrations.jira.indexer import _issue_path as jira_issue_path
from backend.integrations.linear import indexer as linear_indexer
from backend.integrations.linear.indexer import _issue_path as linear_issue_path
from backend.integrations.notion.indexer import _dedupe


def _gmail_message(subject: str) -> dict:
    return {
        "id": "18c7a2b3f4d5e6a7",
        "internalDate": str(int(datetime(2026, 7, 6, 14, 30, tzinfo=UTC).timestamp() * 1000)),
        "payload": {"headers": [{"name": "Subject", "value": subject}]},
    }


def test_gmail_path_is_date_foldered_and_chronological():
    # Year/month folders + a day-time leaf prefix: the mailbox lists by date,
    # not alphabetically by subject or by opaque message id.
    assert (
        _message_path(_gmail_message("Q3 Budget")) == "2026/07/06 1430 Q3 Budget (18c7a2b3f4d5e6a7)"
    )


def test_gmail_path_keeps_subject_out_of_the_folder_tree():
    # A slash in a subject must not fabricate folders.
    path = _message_path(_gmail_message("re: a/b testing"))
    assert path == "2026/07/06 1430 re: a-b testing (18c7a2b3f4d5e6a7)"


def test_gmail_path_requires_id_and_timestamp():
    assert _message_path({"internalDate": "1"}) is None
    assert _message_path({"id": "x"}) is None


def test_linear_path_files_issues_under_their_team_in_numeric_order():
    # Team folders, and zero-padding so FER-2 lists before FER-1000 (bare
    # identifiers sort lexically: FER-1000 < FER-2).
    assert linear_issue_path("FER-199") == "FER/FER-00199"
    assert linear_issue_path("FER-2") < linear_issue_path("FER-1000")


def test_jira_path_lists_the_project_in_numeric_order():
    assert jira_issue_path("PROJ-9") == "PROJ-00009"
    assert jira_issue_path("PROJ-9") < jira_issue_path("PROJ-123")


def test_granola_path_groups_meetings_by_month():
    meeting = {"id": "abc12345-6789", "title": "Standup", "date": "2026-07-04T09:00:00Z"}
    assert _meeting_path(meeting, meeting["id"]) == "2026-07/04 Standup (abc12345)"


def test_granola_path_parses_the_list_blob_date_format():
    # list_meetings dates arrive as "Jun 5, 2026", not ISO — they must still
    # land in a month folder, not all pile into undated/.
    meeting = {"id": "abc12345-6789", "title": "Standup", "date": "Jun 5, 2026"}
    assert _meeting_path(meeting, meeting["id"]) == "2026-06/05 Standup (abc12345)"


def test_granola_path_files_unparseable_dates_visibly():
    meeting = {"id": "abc12345-6789", "title": "Standup", "date": "last Tuesday"}
    assert _meeting_path(meeting, meeting["id"]) == "undated/Standup (abc12345)"


def test_asana_path_mirrors_the_board_section_for_this_project():
    task = {
        "gid": "42",
        "name": "Ship it / fast",
        "memberships": [
            {"project": {"gid": "other-project"}, "section": {"name": "Wrong board"}},
            {"project": {"gid": "proj-1"}, "section": {"name": "In Progress"}},
        ],
    }
    assert _task_path(task, "proj-1") == "In Progress/Ship it - fast (42)"


def test_asana_path_makes_a_missing_section_visible():
    assert _task_path({"gid": "7", "name": "X"}, "proj-1") == "(no section)/X (7)"


def test_notion_dedupe_keeps_same_titled_siblings_distinct():
    # Without the suffix the second sibling would overwrite the first on the
    # (source_id, path) upsert key — a silently dropped document.
    present = ["DB/Untitled"]
    assert _dedupe("DB/Untitled", "deadbeef-0000", present) == "DB/Untitled (deadbeef)"
    assert _dedupe("DB/Fresh", "deadbeef-0000", present) == "DB/Fresh"


@pytest.mark.asyncio
async def test_linear_indexer_writes_team_paths(monkeypatch):
    captured: list[dict] = []
    present: list[list[str]] = []

    async def fake_list_issues(token, cursor):
        return [{"identifier": "FER-199", "title": "Ship", "updated_at": None}], None

    async def fake_token(user_id, provider):
        return "tok"

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    async def capture_remove(table, source_id, paths):
        present.append(paths)

    monkeypatch.setattr(linear_indexer.linear_api_service, "list_issues", fake_list_issues)
    monkeypatch.setattr(linear_indexer, "get_valid_token", fake_token)
    monkeypatch.setattr(linear_indexer.source_service, "upsert_index_row", capture_upsert)
    monkeypatch.setattr(linear_indexer.source_service, "remove_missing_documents", capture_remove)

    await linear_indexer.index_linear(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "owner_user_id": "00000000-0000-0000-0000-000000000002",
        }
    )

    assert captured[0]["path"] == "FER/FER-00199"
    # The name keeps the real identifier — the padded form exists only to sort.
    assert captured[0]["name"] == "FER-199 Ship"
    assert captured[0]["external_ref"] == "FER-199"
    assert present == [["FER/FER-00199"]]


@pytest.mark.asyncio
async def test_granola_indexer_refiles_stored_transcripts_without_refetching(monkeypatch):
    """When a meeting's path moves (title/date edit or path-scheme change), the
    stored transcript must move with it — Granola rate-limits transcript
    fetches, so re-downloading the whole history would wedge the sync."""
    stored_content = "# Standup\n## Transcript\nwe shipped the thing"
    captured: list[dict] = []
    present: list[list[str]] = []

    class FakePool:
        async def fetch(self, query, *args):
            return [{"external_ref": "m1", "path": "m1", "content": stored_content}]

    blob = (
        '<meetings_data count="1">'
        '<meeting id="m1" title="Standup" date="Jun 5, 2026">'
        "<known_participants>sam@x.com</known_participants>"
        "</meeting></meetings_data>"
    )

    async def fake_call_tool_data(session, tool, params):
        assert tool == "list_meetings", "stored transcript must not be refetched"
        return blob

    @asynccontextmanager
    async def fake_session(access_token):
        async def list_tools():
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(name="list_meetings"),
                    SimpleNamespace(name="get_meeting_transcript"),
                ]
            )

        yield SimpleNamespace(list_tools=list_tools)

    async def fake_access_token(user_id):
        return "tok"

    async def capture_upsert(**kwargs):
        captured.append(kwargs)

    async def capture_remove(table, source_id, paths):
        present.append(paths)

    monkeypatch.setattr(granola_indexer, "get_pool", lambda: FakePool())
    monkeypatch.setattr(granola_indexer, "call_tool_data", fake_call_tool_data)
    monkeypatch.setattr(granola_indexer, "granola_session", fake_session)
    monkeypatch.setattr(granola_indexer, "get_valid_access_token", fake_access_token)
    monkeypatch.setattr(granola_indexer.source_service, "upsert_content_document", capture_upsert)
    monkeypatch.setattr(granola_indexer.source_service, "remove_missing_documents", capture_remove)

    await granola_indexer.index_granola(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "owner_user_id": "00000000-0000-0000-0000-000000000002",
        }
    )

    assert captured[0]["path"] == "2026-06/05 Standup (m1)"
    assert captured[0]["content"] == stored_content
    assert present == [["2026-06/05 Standup (m1)"]]
