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


def test_single_blob_upload_publishes_only_the_file_item(monkeypatch, tmp_path) -> None:
    uploaded = tmp_path / "shot.png"
    uploaded.write_bytes(b"png")
    published_items = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def create_folder(self, _workspace_id, name, parent_folder_id=None):
            assert parent_folder_id is None
            return {"id": "folder-1", "name": name}

        def upload_ws_file(self, _workspace_id, path):
            assert path == str(uploaded)
            return {"id": "file-1", "name": uploaded.name, "url": "https://files.test/shot.png"}

        def create_page(self, *_args, **_kwargs):
            return {"id": "page-1"}

        def publish_skill(self, _workspace_id, title, description, items):
            published_items.extend(items)
            return {
                "skill": {"id": "stash-1", "slug": "shot"},
                "url": "https://app.example/skills/shot",
            }

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_resolve_workspace", lambda: "workspace-1")
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(str(uploaded), name="", workspace_id=None, skill="shot", public=True, as_json=False)

    assert published_items == [
        {
            "object_type": "file",
            "object_id": "file-1",
            "position": 0,
            "label_override": "shot.png",
        }
    ]


def test_single_text_upload_publishes_only_the_page_item(monkeypatch, tmp_path) -> None:
    uploaded = tmp_path / "notes.md"
    uploaded.write_text("# Notes")
    published_items = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def create_folder(self, _workspace_id, name, parent_folder_id=None):
            assert parent_folder_id is None
            return {"id": "folder-1", "name": name}

        def create_page(self, _workspace_id, name, content, folder_id):
            assert name == "notes.md"
            assert content == "# Notes"
            assert folder_id == "folder-1"
            return {"id": "page-1"}

        def publish_skill(self, _workspace_id, title, description, items):
            published_items.extend(items)
            return {
                "skill": {"id": "stash-1", "slug": "notes"},
                "url": "https://app.example/skills/notes",
            }

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_resolve_workspace", lambda: "workspace-1")
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(
        str(uploaded), name="", workspace_id=None, skill="notes", public=True, as_json=False
    )

    assert published_items == [
        {
            "object_type": "page",
            "object_id": "page-1",
            "position": 0,
            "label_override": "notes.md",
        }
    ]
