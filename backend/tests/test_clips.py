"""Clips: webpages and binaries saved by the browser extension.

Web clips must land as markdown pages in the Clips root folder with their
source URL both in metadata (structured) and in the body (so FTS and the
curator see it). Binary clips must record source_url on the file row.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient

from backend.services import storage_service
from backend.services.article_extraction import ArticleExtractionError, extract_article
from backend.tasks import extraction

from .conftest import unique_name

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


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['api_key']}"}


def test_extract_article_returns_title_and_markdown() -> None:
    article = extract_article(ARTICLE_HTML, "https://example.com/post")
    assert article["title"] == "Why Simplicity Wins"
    assert "moving part" in article["markdown"]


def test_extract_article_rejects_empty_page() -> None:
    with pytest.raises(ArticleExtractionError):
        extract_article("<html><head></head><body></body></html>", "https://example.com")


@pytest.mark.asyncio
async def test_clip_page_lands_in_clips_folder(client: AsyncClient, pool) -> None:
    headers = await _register(client)

    resp = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://example.com/post", "html": ARTICLE_HTML},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "page"
    assert data["name"] == "Why Simplicity Wins"

    row = await pool.fetchrow(
        "SELECT p.content_markdown, p.metadata, f.name AS folder_name, f.parent_folder_id "
        "FROM pages p JOIN folders f ON f.id = p.folder_id WHERE p.id = $1",
        UUID(data["id"]),
    )
    assert row["folder_name"] == "Clips"
    assert row["parent_folder_id"] is None
    assert row["metadata"]["source_url"] == "https://example.com/post"
    assert "Clipped from <https://example.com/post>" in row["content_markdown"]


@pytest.mark.asyncio
async def test_clip_page_fails_loud_on_unextractable_html(client: AsyncClient) -> None:
    headers = await _register(client)
    resp = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://example.com/empty", "html": "<html><body></body></html>"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "article" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reclip_same_title_creates_new_page(client: AsyncClient) -> None:
    headers = await _register(client)
    first = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://example.com/post", "html": ARTICLE_HTML},
        headers=headers,
    )
    second = await client.post(
        "/api/v1/me/clips/page",
        json={"url": "https://example.com/post", "html": ARTICLE_HTML},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["name"] == "Why Simplicity Wins (2)"


@pytest.mark.asyncio
async def test_clip_file_records_source_url(client: AsyncClient, pool, monkeypatch) -> None:
    headers = await _register(client)

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
        "SELECT fi.source_url, fo.name AS folder_name "
        "FROM files fi JOIN folders fo ON fo.id = fi.folder_id WHERE fi.id = $1",
        UUID(data["id"]),
    )
    assert row["source_url"] == "https://arxiv.org/pdf/2401.00001"
    assert row["folder_name"] == "Clips"


@pytest.mark.asyncio
async def test_clip_file_rejects_markdown(client: AsyncClient) -> None:
    headers = await _register(client)
    resp = await client.post(
        "/api/v1/me/clips/file",
        files={"file": ("note.md", b"# hi", "text/markdown")},
        data={"url": "https://example.com/note"},
        headers=headers,
    )
    assert resp.status_code == 400
