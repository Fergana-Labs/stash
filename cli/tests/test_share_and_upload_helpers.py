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


def _resolver_client(resolved, calls=None):
    """A client whose resolve_session answers with a canned payload.

    Matching a handle to a session is the server's job now, so what the CLI
    owes is narrower: ask once, and use the field the caller needs.
    """

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def resolve_session(self, ref, trashed=False):
            if calls is not None:
                calls.append((ref, trashed))
            return resolved

    return FakeClient


def test_resolve_session_takes_the_id_the_caller_needs(monkeypatch) -> None:
    # share follows the transcript stream id; rm/restore/mv/shares take the
    # row id. One lookup answers both.
    monkeypatch.setattr(
        main,
        "_client",
        _resolver_client(
            {"matched": True, "session_id": "sess-1", "id": "row-1", "name": "Ship the fast path"}
        ),
    )

    assert main._resolve_session("Ship the fast path") == "sess-1"
    assert main._resolve_session("Ship the fast path", field="id") == "row-1"


def test_resolve_session_passes_unmatched_handles_through(monkeypatch) -> None:
    # A handle naming no title is already an id: the server echoes it back, so
    # the CLI needs no branch and the endpoint that uses it rejects it if wrong.
    monkeypatch.setattr(
        main,
        "_client",
        _resolver_client(
            {"matched": False, "session_id": "sess-unknown", "id": "sess-unknown", "name": None}
        ),
    )

    assert main._resolve_session("sess-unknown") == "sess-unknown"


def test_restore_asks_the_trash_and_other_commands_do_not(monkeypatch) -> None:
    # A trashed session is out of the scope listing, so restore has to say so;
    # every other command must not, or it would resolve against the wrong set.
    calls: list = []
    monkeypatch.setattr(
        main,
        "_client",
        _resolver_client({"matched": True, "session_id": "sess-9", "id": "row-9"}, calls),
    )

    assert main._resolve_session_refs([("session", "Abandoned refactor")], trashed=True) == [
        ("session", "row-9")
    ]
    assert calls == [("Abandoned refactor", True)]

    calls.clear()
    assert main._resolve_session_refs([("session", "Live one")]) == [("session", "row-9")]
    assert calls == [("Live one", False)]


def test_non_session_refs_are_never_resolved(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(
        main,
        "_client",
        _resolver_client({"matched": True, "session_id": "sess-9", "id": "row-9"}, calls),
    )

    assert main._resolve_session_refs([("page", "Some page")]) == [("page", "Some page")]
    assert calls == []


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
    converted: list[str] = []

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

        def convert_folder_to_skill(self, folder_id):
            converted.append(folder_id)
            return {"folder_id": folder_id, "name": "shot", "is_skill": True}

        def publish_skill_folder(self, folder_id, **kwargs):
            published["folder_id"] = folder_id
            published["kwargs"] = kwargs
            return {"id": "skill-1", "slug": "shot", "title": "shot"}

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(str(uploaded), name="", skill="shot", public=True, as_json=False)

    # --skill writes the instructions AND marks the folder a skill — writing
    # SKILL.md alone stopped conferring membership when it became a stored flag.
    assert "SKILL.md" in created_pages
    assert converted == ["folder-1"]
    assert published["folder_id"] == "folder-1"


def test_upload_with_skill_flag_private_skips_publish(monkeypatch, tmp_path) -> None:
    uploaded = tmp_path / "notes.md"
    uploaded.write_text("# Notes")
    published: dict = {}
    created_pages: list[str] = []
    converted: list[str] = []

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

        def convert_folder_to_skill(self, folder_id):
            converted.append(folder_id)
            return {"folder_id": folder_id, "name": "notes", "is_skill": True}

        def publish_skill_folder(self, folder_id, **kwargs):
            published["folder_id"] = folder_id
            return {"id": "skill-1", "slug": "notes", "title": "notes"}

    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: FakeClient())

    main.upload(str(uploaded), name="", skill="notes", public=False, as_json=False)

    # Private: the folder becomes a skill (instructions + explicit convert)
    # but nothing is published.
    assert "SKILL.md" in created_pages
    assert converted == ["folder-1"]
    assert published == {}
