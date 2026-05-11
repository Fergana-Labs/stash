from pathlib import Path

from cli.main import _is_upload_text_file, _parse_workspace_id


def test_parse_workspace_id_accepts_bare_id() -> None:
    assert _parse_workspace_id("abc-123") == "abc-123"


def test_parse_workspace_id_accepts_share_url() -> None:
    assert _parse_workspace_id("https://joinstash.ai/s/abc-123?tab=wiki") == "abc-123"


def test_parse_workspace_id_accepts_workspace_url() -> None:
    assert _parse_workspace_id("https://joinstash.ai/workspaces/abc-123/requests") == "abc-123"


def test_upload_text_file_detection() -> None:
    assert _is_upload_text_file(Path("notes.md"))
    assert _is_upload_text_file(Path("script.py"))
    assert not _is_upload_text_file(Path("diagram.png"))
