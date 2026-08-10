"""Agent content edits are guarded: `stash files edit-page --content` must
carry the content_hash from the read the edit is based on, so a concurrent
human edit in the web editor is refused (409) instead of overwritten. The
browser deliberately sends no hash and always wins; agents are the party
that re-reads and retries.
"""

from __future__ import annotations

from unittest import mock

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_content_edit_without_hash_is_refused() -> None:
    with mock.patch("cli.main._client") as client_factory:
        result = runner.invoke(app, ["files", "edit-page", "page-1", "--content", "new text"])
    assert result.exit_code == 1
    assert "--expected-content-hash" in result.output
    client_factory.return_value.__enter__.return_value.update_page.assert_not_called()


def test_content_edit_passes_hash_through() -> None:
    with mock.patch("cli.main._client") as client_factory:
        client = client_factory.return_value.__enter__.return_value
        client.update_page.return_value = {"id": "page-1", "name": "Doc"}
        result = runner.invoke(
            app,
            [
                "files",
                "edit-page",
                "page-1",
                "--content",
                "new text",
                "--expected-content-hash",
                "abc123",
            ],
        )
    assert result.exit_code == 0
    client.update_page.assert_called_once_with(
        "page-1", content="new text", expected_content_hash="abc123"
    )


def test_rename_alone_needs_no_hash() -> None:
    """Renames don't replace content, so they carry no fingerprint."""
    with mock.patch("cli.main._client") as client_factory:
        client = client_factory.return_value.__enter__.return_value
        client.update_page.return_value = {"id": "page-1", "name": "New name"}
        result = runner.invoke(app, ["files", "edit-page", "page-1", "--name", "New name"])
    assert result.exit_code == 0
    client.update_page.assert_called_once_with("page-1", name="New name")
