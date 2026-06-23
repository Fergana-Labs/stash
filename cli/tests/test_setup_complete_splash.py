from cli import main


def test_setup_complete_intro_prompts_connect_when_not_connected() -> None:
    intro = main._setup_complete_intro("", connected=False)

    assert "No repo is connected yet" in intro
    assert "stash connect" in intro
    assert "See your Stash" not in intro


def test_setup_complete_intro_includes_stash_link_when_connected() -> None:
    intro = main._setup_complete_intro("http://localhost:3457/me", connected=True)

    assert "See your Stash" in intro
    assert "http://localhost:3457/me" in intro
    assert "You're streaming" in intro
    assert "No repo is connected yet" not in intro
