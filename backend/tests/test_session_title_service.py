from backend.services.session_title_service import title_from_events, title_from_text


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
