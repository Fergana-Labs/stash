from cli import main


def test_setup_complete_intro_prompts_connect_when_no_workspace() -> None:
    intro = main._setup_complete_intro("")

    assert "No repo is connected yet" in intro
    assert "stash connect" in intro
    assert "Commit the [cyan].stash[/cyan]" not in intro
    assert "See your workspace" not in intro


def test_setup_complete_intro_includes_workspace_link_when_connected() -> None:
    intro = main._setup_complete_intro("http://localhost:3457/workspaces/workspace-1")

    assert "See your workspace" in intro
    assert "http://localhost:3457/workspaces/workspace-1" in intro
    assert "Commit the [cyan].stash[/cyan]" in intro
    assert "No repo is connected yet" not in intro
