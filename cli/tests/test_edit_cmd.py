"""`stash edit` is the top-level counterpart to `stash upload`: upload creates
new items, edit changes an existing page. These lock in the wiring — the right
update_page call — plus the ergonomics that make it agent-friendly: accepting
the app URL upload printed, and --append not clobbering the existing body."""

import pytest
import typer

from cli import main
from cli.main import _parse_page_ref


class _FakeClient:
    def __init__(self, calls: list, page: dict | None = None):
        self._calls = calls
        self._page = page or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get_page(self, page_id):
        self._calls.append(("get_page", page_id))
        return self._page

    def update_page(self, page_id, **kwargs):
        self._calls.append(("update_page", page_id, kwargs))
        return {"id": page_id, "name": kwargs.get("name", "Page")}


def _wire(monkeypatch, page: dict | None = None) -> list:
    calls: list = []
    monkeypatch.setattr(main, "_require_auth", lambda: None)
    monkeypatch.setattr(main, "_client", lambda: _FakeClient(calls, page))
    monkeypatch.setattr(main.telemetry, "record", lambda *_a, **_k: None)
    return calls


def test_parse_page_ref_accepts_raw_id_and_app_url() -> None:
    assert _parse_page_ref("abc-123") == "abc-123"
    assert _parse_page_ref("https://app.joinstash.ai/p/abc-123") == "abc-123"
    assert _parse_page_ref("https://app.joinstash.ai/p/abc-123/") == "abc-123"


def test_edit_replaces_content(monkeypatch) -> None:
    calls = _wire(monkeypatch)
    main.edit(
        "p1",
        content="new body",
        append=None,
        name=None,
        page_type=None,
        html_file=None,
        layout=None,
        attach=None,
        as_json=True,
    )
    assert calls == [("update_page", "p1", {"content": "new body"})]


def test_edit_append_keeps_existing_body(monkeypatch) -> None:
    calls = _wire(monkeypatch, page={"content_type": "markdown", "content_markdown": "# Notes\n"})
    main.edit(
        "https://app.joinstash.ai/p/p1",
        content=None,
        append="hello",
        name=None,
        page_type=None,
        html_file=None,
        layout=None,
        attach=None,
        as_json=True,
    )
    assert calls == [
        ("get_page", "p1"),
        ("update_page", "p1", {"content": "# Notes\n\nhello"}),
    ]


def test_edit_append_rejects_html_pages(monkeypatch) -> None:
    _wire(monkeypatch, page={"content_type": "html", "content_markdown": ""})
    with pytest.raises(typer.Exit):
        main.edit(
            "p1",
            content=None,
            append="hello",
            name=None,
            page_type=None,
            html_file=None,
            layout=None,
            attach=None,
            as_json=True,
        )


def test_edit_append_conflicts_with_content(monkeypatch) -> None:
    _wire(monkeypatch)
    with pytest.raises(typer.Exit):
        main.edit(
            "p1",
            content="body",
            append="hello",
            name=None,
            page_type=None,
            html_file=None,
            layout=None,
            attach=None,
            as_json=True,
        )
