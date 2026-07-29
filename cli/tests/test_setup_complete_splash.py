from cli import main


def test_setup_complete_intro_prompts_connect_when_not_connected() -> None:
    intro = main._setup_complete_intro("http://localhost:3457", connected=False, recording=True)

    assert "stash connect" in intro
    assert "git repo or not" in intro


def test_setup_complete_intro_omits_connect_prompt_when_connected() -> None:
    intro = main._setup_complete_intro("http://localhost:3457", connected=True, recording=True)

    assert "stash connect" not in intro


def test_setup_complete_intro_always_links_home() -> None:
    for connected in (False, True):
        intro = main._setup_complete_intro(
            "http://localhost:3457/me", connected=connected, recording=True
        )
        assert "See your Stash" in intro
        assert "http://localhost:3457/me" in intro


def test_setup_complete_intro_states_recording_on() -> None:
    intro = main._setup_complete_intro("http://localhost:3457", connected=True, recording=True)

    assert "You're recording" in intro
    assert "Recording is off" not in intro


def test_setup_complete_intro_states_recording_off_with_way_back_in() -> None:
    # Declining recording must never be a dead end: the splash has to name the
    # commands that turn it back on.
    intro = main._setup_complete_intro("http://localhost:3457", connected=True, recording=False)

    assert "Recording is off" in intro
    assert "stash start" in intro
    assert "stash setup" in intro
