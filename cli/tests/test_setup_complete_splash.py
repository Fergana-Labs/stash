from cli import main

MEMORY_URL = "http://localhost:3457/memory"


def _intro(connected=True, recording=True, importing=None):
    return main._setup_complete_intro(
        MEMORY_URL, connected=connected, recording=recording, importing=importing
    )


def test_setup_complete_intro_prompts_connect_when_not_connected() -> None:
    intro = _intro(connected=False)

    assert "stash connect" in intro
    assert "CLAUDE.md" in intro


def test_setup_complete_intro_omits_connect_prompt_when_connected() -> None:
    assert "stash connect" not in _intro(connected=True)


def test_setup_complete_intro_always_links_memory() -> None:
    for connected in (False, True):
        intro = _intro(connected=connected)
        assert "See your knowledge base" in intro
        assert MEMORY_URL in intro


def test_setup_complete_intro_states_recording_on() -> None:
    intro = _intro(recording=True)

    assert "You're recording" in intro
    assert "Recording is off" not in intro


def test_setup_complete_intro_states_recording_off_with_way_back_in() -> None:
    # Declining recording must never be a dead end: the splash has to name the
    # commands that turn it back on.
    intro = _intro(recording=False)

    assert "Recording is off" in intro
    assert "stash start" in intro
    assert "stash setup" in intro


def test_setup_complete_intro_shows_running_import_with_counts() -> None:
    intro = _intro(importing={"done": 120, "total": 6193})

    assert "Your history is uploading right now" in intro
    assert "120/6193" in intro
    assert "stash import-history --status" in intro


def test_setup_complete_intro_omits_import_section_when_no_import() -> None:
    assert "uploading right now" not in _intro(importing=None)
