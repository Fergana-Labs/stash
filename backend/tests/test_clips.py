"""Clips: webpages and binaries saved by the browser extension.

A saved page is stored as HTML (the extension sends readable article HTML)
under Clips/raw, and every save adds a row to the Bookmarks table under
Clips. Binary clips (PDFs) land in Clips/raw too and record source_url.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import storage_service
from backend.services.article_extraction import ArticleExtractionError, extract_article
from backend.tasks import extraction

from .conftest import unique_name


async def _register(client: AsyncClient) -> tuple[dict, UUID]:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, UUID(body["id"])


async def _bookmark_rows(pool, owner_id: UUID) -> list[dict]:
    """Rows of the owner's Bookmarks table, keyed by column NAME (not id)."""
    table = await pool.fetchrow(
        "SELECT t.id, t.columns FROM tables t JOIN folders f ON f.id = t.folder_id "
        "WHERE t.owner_user_id = $1 AND f.name = 'Clips' AND t.name = 'Bookmarks'",
        owner_id,
    )
    if table is None:
        return []
    id_to_name = {c["id"]: c["name"] for c in table["columns"]}
    rows = await pool.fetch(
        "SELECT data FROM table_rows WHERE table_id = $1 ORDER BY row_order", table["id"]
    )
    return [{id_to_name[k]: v for k, v in r["data"].items()} for r in rows]


_PARAGRAPH = (
    "Simplicity is the most important property a codebase can have, because "
    "every additional moving part multiplies the number of states the team "
    "has to reason about when something goes wrong in production. "
)

ARTICLE_HTML = f"""<html>
<head><title>Why Simplicity Wins | Some Blog</title></head>
<body>
<article>
<h1>Why Simplicity Wins</h1>
<p>{_PARAGRAPH * 3}</p>
<p>{_PARAGRAPH * 3}</p>
<p>{_PARAGRAPH * 3}</p>
</article>
</body>
</html>"""


def test_extract_article_returns_title_and_markdown() -> None:
    article = extract_article(ARTICLE_HTML, "https://example.com/post")
    assert article["title"] == "Why Simplicity Wins"
    assert "moving part" in article["markdown"]


def test_extract_article_rejects_empty_page() -> None:
    with pytest.raises(ArticleExtractionError):
        extract_article("<html><head></head><body></body></html>", "https://example.com")


@pytest.mark.asyncio
async def test_clip_page_stores_html_in_raw_and_adds_bookmark(client: AsyncClient, pool) -> None:
    headers, owner_id = await _register(client)

    resp = await client.post(
        "/api/v1/me/clips/page",
        json={
            "url": "https://www.example.com/post",
            "title": "Why Simplicity Wins",
            "html": ARTICLE_HTML,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "page"
    assert data["name"] == "Why Simplicity Wins"

    row = await pool.fetchrow(
        "SELECT p.content_html, p.content_type, p.metadata, f.name AS folder_name, "
        "gp.name AS parent_name "
        "FROM pages p JOIN folders f ON f.id = p.folder_id "
        "JOIN folders gp ON gp.id = f.parent_folder_id WHERE p.id = $1",
        UUID(data["id"]),
    )
    assert row["folder_name"] == "raw"
    assert row["parent_name"] == "Clips"
    assert row["content_type"] == "html"
    assert "Why Simplicity Wins" in row["content_html"]  # the article HTML is kept
    assert "Saved from" in row["content_html"]
    assert row["metadata"]["source_url"] == "https://www.example.com/post"

    bookmarks = await _bookmark_rows(pool, owner_id)
    assert len(bookmarks) == 1
    assert bookmarks[0]["Title"] == "Why Simplicity Wins"
    assert bookmarks[0]["URL"] == "https://www.example.com/post"
    assert bookmarks[0]["Type"] == "Page"
    assert bookmarks[0]["Site"] == "example.com"  # www. stripped
    assert bookmarks[0]["Clip"].endswith(f"/p/{data['id']}")


@pytest.mark.asyncio
async def test_clip_page_requires_a_title(client: AsyncClient) -> None:
    headers, _ = await _register(client)
    resp = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://example.com/notitle", "html": ARTICLE_HTML},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "title" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reclip_same_title_creates_new_page(client: AsyncClient, pool) -> None:
    headers, owner_id = await _register(client)
    body = {"url": "https://example.com/post", "title": "Why Simplicity Wins", "html": ARTICLE_HTML}
    first = await client.post("/api/v1/me/clips/page", json=body, headers=headers)
    second = await client.post("/api/v1/me/clips/page", json=body, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["name"] == "Why Simplicity Wins (2)"
    # Two saves → two bookmark rows.
    assert len(await _bookmark_rows(pool, owner_id)) == 2


@pytest.mark.asyncio
async def test_clip_file_lands_in_raw_and_adds_bookmark(
    client: AsyncClient, pool, monkeypatch
) -> None:
    headers, owner_id = await _register(client)

    async def _upload(*args, **kwargs):
        return "test/storage-key"

    async def _url(key):
        return f"https://blob.example/{key}"

    monkeypatch.setattr(storage_service, "is_configured", lambda: True)
    monkeypatch.setattr(storage_service, "upload_file", _upload)
    monkeypatch.setattr(storage_service, "get_file_url", _url)
    monkeypatch.setattr(extraction.extract_file_text, "delay", lambda *a, **k: None)

    resp = await client.post(
        "/api/v1/me/clips/file",
        files={"file": ("paper.pdf", b"%PDF-1.4 fake body", "application/pdf")},
        data={"url": "https://arxiv.org/pdf/2401.00001"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "file"

    row = await pool.fetchrow(
        "SELECT fi.source_url, fo.name AS folder_name, gp.name AS parent_name "
        "FROM files fi JOIN folders fo ON fo.id = fi.folder_id "
        "JOIN folders gp ON gp.id = fo.parent_folder_id WHERE fi.id = $1",
        UUID(data["id"]),
    )
    assert row["source_url"] == "https://arxiv.org/pdf/2401.00001"
    assert row["folder_name"] == "raw"
    assert row["parent_name"] == "Clips"

    bookmarks = await _bookmark_rows(pool, owner_id)
    assert len(bookmarks) == 1
    assert bookmarks[0]["Type"] == "PDF"
    assert bookmarks[0]["Clip"].endswith(f"/f/{data['id']}")


@pytest.mark.asyncio
async def test_clip_file_rejects_markdown(client: AsyncClient) -> None:
    headers, _ = await _register(client)
    resp = await client.post(
        "/api/v1/me/clips/file",
        files={"file": ("note.md", b"# hi", "text/markdown")},
        data={"url": "https://example.com/note"},
        headers=headers,
    )
    assert resp.status_code == 400
