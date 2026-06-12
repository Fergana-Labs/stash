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


def test_skill_url_uses_web_app_url(monkeypatch) -> None:
    monkeypatch.setattr(main, "_web_app_url", lambda: "https://app.example")

    assert main._skill_url({"slug": "demo-stash"}) == "https://app.example/skills/demo-stash"


def test_file_app_url_is_canonical_and_workspace_free(monkeypatch) -> None:
    workspace_id = uuid4()
    file_id = uuid4()
    monkeypatch.setattr(settings, "PUBLIC_URL", "https://app.example/")

    # Canonical: the workspace is resolved server-side, so the URL must not
    # embed it — that's what keeps shared file links from going stale.
    assert (
        _file_app_url({"workspace_id": workspace_id, "id": file_id})
        == f"https://app.example/f/{file_id}"
    )


def test_upload_with_skill_flag_publishes_the_folder(monkeypatch, tmp_path) -> None:
    uploaded = tmp_path / "shot.png"
    uploaded.write_bytes(b"png")
    published: dict = {}
    created_pages: list[str] = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def create_folder(self, _workspace_id, name, parent_folder_id=None):
            assert parent_folder_id is None
            return {"id": "folder-1", "name": name}

        def upload_ws_file(self, _workspace_id, path, folder_id=None):
            assert path == str(uploaded)
            return {"id": "file-1", "name": uploaded.name, "url": "https://files.test/shot.png"}

        def create_page(self, _workspace_id, name, content="", folder_id=None, content_type=None):
            created_pages.append(name)
            return {"id": f"page-{len(created_pages)}"}

        def publish_skill_folder(self, _workspace_id, folder_id, **kwargs):
            published["folder_id"] = folder_id
            published["kwargs"] = kwargs
            return {"id": "skill-1", "slug": "shot", "title": "shot"}

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_resolve_workspace", lambda: "workspace-1")
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(str(uploaded), name="", workspace_id=None, skill="shot", public=True, as_json=False)

    # --skill makes the folder a skill (SKILL.md) and --public publishes it.
    assert "SKILL.md" in created_pages
    assert published["folder_id"] == "folder-1"


def test_upload_with_skill_flag_private_skips_publish(monkeypatch, tmp_path) -> None:
    uploaded = tmp_path / "notes.md"
    uploaded.write_text("# Notes")
    published: dict = {}
    created_pages: list[str] = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def create_folder(self, _workspace_id, name, parent_folder_id=None):
            assert parent_folder_id is None
            return {"id": "folder-1", "name": name}

        def create_page(self, _workspace_id, name, content="", folder_id=None, content_type=None):
            created_pages.append(name)
            assert folder_id == "folder-1"
            return {"id": f"page-{len(created_pages)}"}

        def publish_skill_folder(self, _workspace_id, folder_id, **kwargs):
            published["folder_id"] = folder_id
            return {"id": "skill-1", "slug": "notes", "title": "notes"}

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_resolve_workspace", lambda: "workspace-1")
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(
        str(uploaded), name="", workspace_id=None, skill="notes", public=False, as_json=False
    )

    # Private: the folder becomes a skill (SKILL.md) but nothing is published.
    assert "SKILL.md" in created_pages
    assert published == {}
