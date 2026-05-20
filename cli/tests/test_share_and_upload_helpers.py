from pathlib import Path
from uuid import uuid4

from backend.config import settings
from backend.routers.files import _file_app_url
from cli import main
from cli.main import _is_upload_text_file


def test_upload_text_file_detection() -> None:
    assert _is_upload_text_file(Path("notes.md"))
    assert _is_upload_text_file(Path("script.py"))
    assert not _is_upload_text_file(Path("diagram.png"))


def test_stash_url_uses_web_app_url(monkeypatch) -> None:
    monkeypatch.setattr(main, "_web_app_url", lambda: "https://app.example")

    assert main._stash_url({"slug": "demo-stash"}) == "https://app.example/stashes/demo-stash"


def test_file_app_url_points_to_workspace_file_viewer(monkeypatch) -> None:
    workspace_id = uuid4()
    file_id = uuid4()
    monkeypatch.setattr(settings, "PUBLIC_URL", "https://app.example/")

    assert (
        _file_app_url({"workspace_id": workspace_id, "id": file_id})
        == f"https://app.example/workspaces/{workspace_id}/f/{file_id}"
    )
