from backend.services.session_title_service import title_from_summary


def test_title_from_summary_skips_generic_markdown_heading():
    title = title_from_summary(
        "## Session Summary\n\nAdded a new API route for members. Updated tests.",
        "session-1",
    )

    assert title == "Added a new API route for members"


def test_title_from_summary_strips_inline_generic_label():
    title = title_from_summary(
        "**Session Summary:** Added member invitations to the API. Documented the route.",
        "session-1",
    )

    assert title == "Added member invitations to the API"


def test_title_from_summary_skips_generic_section_heading():
    title = title_from_summary(
        "## Session Summary\n\n### What changed\n\n- Added member invitation routes.",
        "session-1",
    )

    assert title == "Added member invitation routes"


def test_title_from_summary_falls_back_to_session_id_for_empty_summary():
    assert title_from_summary("## Session Summary", "session-1") == "session-1"
