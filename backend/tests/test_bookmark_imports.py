"""Bookmark and tab imports.

An import must mirror the browser's folder tree under Clips/Bookmarks,
survive the malformed HTML real exports produce, drop non-http schemes
instead of failing on them, and report per-URL failures through the batch
progress endpoint — one dead link can never sink a 10k import.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import bookmarks_parser, clip_router
from backend.tasks import clips as clips_tasks

from .conftest import unique_name
from .test_clips import ARTICLE_HTML

BOOKMARKS_HTML = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1700000000" PERSONAL_TOOLBAR_FOLDER="true">Bookmarks bar</H3>
    <DL><p>
        <DT><A HREF="https://example.com/one" ADD_DATE="1700000001">First &amp; finest</A>
        <DT><H3 ADD_DATE="1700000002">Research</H3>
        <DL><p>
            <DT><A HREF="https://example.com/two" ADD_DATE="1700000003">Second</A>
            <DT><A HREF="javascript:alert(1)" ADD_DATE="1700000004">Bookmarklet</A>
            <DT><A HREF="https://example.com/one" ADD_DATE="1700000005">Duplicate of first</A>
        </DL><p>
    </DL><p>
    <DT><A HREF="https://example.com/root">Rootless</A>
</DL><p>
"""


async def _register(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["id"]


# --- Parser ---


def test_parse_bookmarks_mirrors_folders_and_drops_junk() -> None:
    bookmarks = bookmarks_parser.parse_bookmarks(BOOKMARKS_HTML)
    assert [(b["url"], b["folder_path"]) for b in bookmarks] == [
        ("https://example.com/one", ("Bookmarks bar",)),
        ("https://example.com/two", ("Bookmarks bar", "Research")),
        ("https://example.com/root", ()),
    ]
    assert bookmarks[0]["title"] == "First & finest"
    assert bookmarks[0]["add_date"] == "1700000001"


def test_parse_bookmarks_survives_unclosed_tags() -> None:
    # Real exports omit </DT> everywhere and sometimes </A>; the parser
    # must not lose entries over it.
    ragged = "<DL><DT><H3>F</H3><DL><DT><A HREF='https://a.example/x'>X</DL></DL>"
    bookmarks = bookmarks_parser.parse_bookmarks(ragged)
    assert [(b["url"], b["folder_path"]) for b in bookmarks] == [("https://a.example/x", ("F",))]


# --- Endpoints ---


def _upload_kwargs(html: str = BOOKMARKS_HTML) -> dict:
    return {"files": {"file": ("bookmarks.html", html.encode(), "text/html")}}


@pytest.mark.asyncio
async def test_bookmark_import_enqueues_all_urls(client: AsyncClient, pool, monkeypatch) -> None:
    dispatched: list[list[str]] = []
    monkeypatch.setattr(
        clips_tasks.process_url_imports, "delay", lambda ids: dispatched.append(ids)
    )
    headers, owner_id = await _register(client)

    resp = await client.post("/api/v1/me/imports/bookmarks", headers=headers, **_upload_kwargs())
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == 3
    assert len(dispatched) == 1 and len(dispatched[0]) == 3

    # Every URL is queued (deduped, junk schemes dropped); the worker files each
    # into Clips/raw + the Bookmarks table, so no folder tree is mirrored.
    rows = await pool.fetch(
        "SELECT url, folder_id FROM url_imports WHERE owner_user_id = $1 ORDER BY url",
        UUID(owner_id),
    )
    assert [r["url"] for r in rows] == [
        "https://example.com/one",
        "https://example.com/root",
        "https://example.com/two",
    ]
    assert all(r["folder_id"] is None for r in rows)


@pytest.mark.asyncio
async def test_reimporting_skips_already_imported_urls(
    client: AsyncClient, pool, monkeypatch
) -> None:
    """Re-importing a bookmarks file (or overlapping tab sets) must not
    re-clip the owner's library — known URLs are skipped and reported."""
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    headers, owner_id = await _register(client)

    first = await client.post("/api/v1/me/imports/bookmarks", headers=headers, **_upload_kwargs())
    assert first.json() == {**first.json(), "total": 3, "skipped": 0}

    again = await client.post("/api/v1/me/imports/bookmarks", headers=headers, **_upload_kwargs())
    body = again.json()
    assert body["total"] == 0
    assert body["skipped"] == 3
    rows = await pool.fetchval(
        "SELECT count(*) FROM url_imports WHERE owner_user_id = $1", UUID(owner_id)
    )
    assert rows == 3

    # Another owner importing the same file is unaffected by this owner's history.
    other_headers, _ = await _register(client)
    other = await client.post(
        "/api/v1/me/imports/bookmarks", headers=other_headers, **_upload_kwargs()
    )
    assert other.json()["total"] == 3


@pytest.mark.asyncio
async def test_bookmark_import_rejects_empty_and_oversized(
    client: AsyncClient, monkeypatch
) -> None:
    headers, _ = await _register(client)

    empty = await client.post(
        "/api/v1/me/imports/bookmarks",
        headers=headers,
        **_upload_kwargs("<DL></DL>"),
    )
    assert empty.status_code == 400

    from backend.routers import clips as clips_router_module

    monkeypatch.setattr(clips_router_module, "MAX_IMPORT_URLS", 2)
    too_big = await client.post("/api/v1/me/imports/bookmarks", headers=headers, **_upload_kwargs())
    assert too_big.status_code == 413
    assert "max 2" in too_big.json()["detail"]


@pytest.mark.asyncio
async def test_tabs_import_enqueues_deduped(client: AsyncClient, pool, monkeypatch) -> None:
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    headers, owner_id = await _register(client)

    resp = await client.post(
        "/api/v1/me/imports/tabs",
        json={"urls": ["https://example.com/a", "https://example.com/b", "https://example.com/a"]},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["total"] == 2  # deduped

    rows = await pool.fetch(
        "SELECT url, folder_id FROM url_imports WHERE owner_user_id = $1", UUID(owner_id)
    )
    assert len(rows) == 2
    assert all(r["folder_id"] is None for r in rows)


@pytest.mark.asyncio
async def test_import_progress_reports_failures_per_url(
    client: AsyncClient, pool, monkeypatch
) -> None:
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    headers, owner_id = await _register(client)

    resp = await client.post("/api/v1/me/imports/bookmarks", headers=headers, **_upload_kwargs())
    batch_id = resp.json()["import_id"]

    async def fake_fetch(url: str):
        if url.endswith("/two"):
            raise ValueError("dead link")
        return ARTICLE_HTML.encode(), "text/html"

    monkeypatch.setattr(clip_router, "_fetch", fake_fetch)
    # Put the dead link on its last attempt so its failure is terminal.
    await pool.execute(
        "UPDATE url_imports SET attempts = 2 WHERE owner_user_id = $1 AND url LIKE '%/two'",
        UUID(owner_id),
    )
    ids = [
        r["id"]
        for r in await pool.fetch(
            "SELECT id FROM url_imports WHERE owner_user_id = $1", UUID(owner_id)
        )
    ]
    await clips_tasks._process_batch(ids)

    progress = await client.get(f"/api/v1/me/imports/{batch_id}", headers=headers)
    assert progress.status_code == 200
    body = progress.json()
    assert body["total"] == 3
    assert body["done"] == 2
    # Terminal failures keep the bookmark as a link-only row and surface in
    # the failures list — the batch drains to zero pending.
    assert body["link_only"] == 1
    assert body["pending"] == 0
    assert body["failures"][0]["url"] == "https://example.com/two"
    assert "dead link" in body["failures"][0]["error"]


@pytest.mark.asyncio
async def test_imports_list_reports_progress_per_batch(client: AsyncClient, monkeypatch) -> None:
    # The app-side progress pill lists all recent batches with aggregate
    # counts — a days-long import must be visible outside the extension popup.
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    headers, owner_id = await _register(client)

    resp = await client.post("/api/v1/me/imports/bookmarks", headers=headers, **_upload_kwargs())
    batch_id = resp.json()["import_id"]

    listing = await client.get("/api/v1/me/imports", headers=headers)
    assert listing.status_code == 200
    batches = listing.json()["batches"]
    assert [b["id"] for b in batches] == [batch_id]
    assert batches[0]["total"] == 3
    assert batches[0]["pending"] == 3
    assert batches[0]["done"] == 0

    # Owner-scoped: another user sees nothing.
    other_headers, _ = await _register(client)
    other = await client.get("/api/v1/me/imports", headers=other_headers)
    assert other.json()["batches"] == []


@pytest.mark.asyncio
async def test_import_progress_is_owner_scoped(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(clips_tasks.process_url_imports, "delay", lambda ids: None)
    headers, _ = await _register(client)
    other_headers, _ = await _register(client)

    resp = await client.post("/api/v1/me/imports/bookmarks", headers=headers, **_upload_kwargs())
    batch_id = resp.json()["import_id"]

    other = await client.get(f"/api/v1/me/imports/{batch_id}", headers=other_headers)
    assert other.status_code == 404
