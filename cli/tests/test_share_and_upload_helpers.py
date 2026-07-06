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


def test_parse_file_ref_accepts_id_and_embed_link() -> None:
    # Pages embed attachments as /api/v1/me/files/<id>/download; agents can
    # paste that link straight into `stash files download`.
    assert main._parse_file_ref("abc-123") == "abc-123"
    assert main._parse_file_ref("/api/v1/me/files/abc-123/download") == "abc-123"


def test_skill_url_uses_web_app_url(monkeypatch) -> None:
    monkeypatch.setattr(main, "_web_app_url", lambda: "https://app.example")

    assert main._skill_url({"slug": "demo-stash"}) == "https://app.example/skills/demo-stash"


def test_file_app_url_is_canonical(monkeypatch) -> None:
    file_id = uuid4()
    monkeypatch.setattr(settings, "PUBLIC_URL", "https://app.example/")

    assert _file_app_url({"id": file_id}) == f"https://app.example/f/{file_id}"


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

        def create_folder(self, name, parent_folder_id=None):
            assert parent_folder_id is None
            return {"id": "folder-1", "name": name}

        def upload_file(self, path, folder_id=None):
            assert path == str(uploaded)
            return {"id": "file-1", "name": uploaded.name, "url": "https://files.test/shot.png"}

        def create_page(self, name, content="", folder_id=None, content_type=None):
            created_pages.append(name)
            return {"id": f"page-{len(created_pages)}"}

        def publish_skill_folder(self, folder_id, **kwargs):
            published["folder_id"] = folder_id
            published["kwargs"] = kwargs
            return {"id": "skill-1", "slug": "shot", "title": "shot"}

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(str(uploaded), name="", skill="shot", public=True, as_json=False)

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

        def create_folder(self, name, parent_folder_id=None):
            assert parent_folder_id is None
            return {"id": "folder-1", "name": name}

        def create_page(self, name, content="", folder_id=None, content_type=None):
            created_pages.append(name)
            assert folder_id == "folder-1"
            return {"id": f"page-{len(created_pages)}"}

        def publish_skill_folder(self, folder_id, **kwargs):
            published["folder_id"] = folder_id
            return {"id": "skill-1", "slug": "notes", "title": "notes"}

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(str(uploaded), name="", skill="notes", public=False, as_json=False)

    # Private: the folder becomes a skill (SKILL.md) but nothing is published.
    assert "SKILL.md" in created_pages
    assert published == {}
