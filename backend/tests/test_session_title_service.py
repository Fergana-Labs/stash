from uuid import UUID

import pytest

from backend.services import session_title_service
from backend.services.session_title_service import (
    clean_generated_title,
    title_from_events,
    title_from_text,
)


def test_title_from_text_uses_first_non_empty_line():
    title = title_from_text(
        "\n\ncan you read this PRD for Stash - does it contradict itself anywhere?\n\nhttps://example.com",
        "session-1",
    )

    assert title == "Read this PRD for Stash - does it contradict itself anywhere"


def test_title_from_events_prefers_user_prompt():
    title = title_from_events(
        [
            {
                "event_type": "assistant_message",
                "content": "I read the PRD and found contradictions.",
            },
            {
                "event_type": "user_message",
                "content": "Find contradictions in the Stash PRD.",
            },
        ],
        "session-1",
    )

    assert title == "Find contradictions in the Stash PRD"


def test_title_from_events_falls_back_to_assistant_message():
    title = title_from_events(
        [
            {
                "event_type": "assistant_message",
                "content": "Implemented auth checks. Updated tests.",
            },
        ],
        "session-1",
    )

    assert title == "Implemented auth checks"


def test_title_from_text_uses_linear_issue_title():
    title = title_from_text(
        """
        You are working on a Linear ticket `FER-19`

        Issue context:
        Identifier: FER-19
        Title: Update the Stash homepage background
        Current status: In Progress
        """,
        "session-1",
    )

    assert title == "Update the Stash homepage background"


def test_title_from_text_falls_back_to_session_id_for_empty_text():
    assert title_from_text("", "session-1") == "session-1"


def test_clean_generated_title_rejects_replies_to_the_transcript():
    # The 2026-05 backfill cached these verbatim as titles; the model was
    # conversing with the transcript instead of naming the task.
    assert clean_generated_title("You're right—I apologize for the confusion") == ""
    assert clean_generated_title("Yes—the proxy won't help here") == ""
    assert clean_generated_title("Your design is solid") == ""
    assert clean_generated_title("Perfect!") == ""


def test_clean_generated_title_rejects_refusals():
    assert clean_generated_title("I need more context to generate a title") == ""
    assert clean_generated_title("I'll help you explore this codebase") == ""
    assert clean_generated_title("I don't have access to your previous sessions") == ""


def test_clean_generated_title_keeps_task_shaped_titles():
    assert clean_generated_title("Fix session title generation") == ("Fix session title generation")
    assert clean_generated_title("Investigate stream closed errors") == (
        "Investigate stream closed errors"
    )


def test_clean_generated_title_strips_markdown_heading_prefixes():
    assert clean_generated_title("# Update CLI API Shape for Stash Publishing") == (
        "Update CLI API Shape for Stash Publishing"
    )
    assert clean_generated_title("Title: **Review Stash PRD for Contradictions**") == (
        "Review Stash PRD for Contradictions"
    )


@pytest.mark.asyncio
async def test_titles_for_sessions_prefers_generated_cache(monkeypatch):
    class Pool:
        async def fetch(self, *args):
            return [
                {
                    "session_id": "s1",
                    "title": "Fix Authentication Flow",
                    "source_hash": "stale",
                }
            ]

    monkeypatch.setattr(session_title_service, "get_pool", lambda: Pool())

    titles = await session_title_service.titles_for_sessions(
        UUID("00000000-0000-0000-0000-000000000001"),
        [
            {
                "session_id": "s1",
                "title_source": "can you fix auth?",
                "event_count": 2,
                "last_at": "2026-05-20T00:00:00Z",
            }
        ],
        enqueue_missing=False,
    )

    assert titles == {"s1": "Fix Authentication Flow"}


@pytest.mark.asyncio
async def test_titles_for_sessions_falls_back_while_title_is_missing(monkeypatch):
    class Pool:
        async def fetch(self, *args):
            return []

    monkeypatch.setattr(session_title_service, "get_pool", lambda: Pool())

    titles = await session_title_service.titles_for_sessions(
        UUID("00000000-0000-0000-0000-000000000001"),
        [
            {
                "session_id": "s1",
                "title_source": "can you fix auth?",
                "event_count": 2,
                "last_at": "2026-05-20T00:00:00Z",
            }
        ],
        enqueue_missing=False,
    )

    assert titles == {"s1": "Fix auth"}
