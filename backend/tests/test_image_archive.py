"""Image archiving for clips.

A clip must become self-contained: its image references are copied into
public storage and rewritten at save time. A failed image keeps its
original hotlink (never lose the article over an image), and the whole
pass is inert until the public bucket is configured.
"""

import httpx
import pytest

from backend.services import image_archive_service, storage_service


class _Response:
    def __init__(self, content_type: str = "image/png", body: bytes = b"png-bytes"):
        self.headers = {"content-type": content_type}
        self.content = body

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    """Serves canned responses by URL; raises for URLs marked broken."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.fetched: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url: str) -> _Response:
        self.fetched.append(url)
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return result


def _enable(monkeypatch, uploads: list):
    async def fake_upload(filename: str, content: bytes, content_type: str) -> str:
        uploads.append((filename, content_type))
        return f"https://media.example/{len(uploads)}/{filename}"

    monkeypatch.setattr(storage_service, "public_media_enabled", lambda: True)
    monkeypatch.setattr(storage_service, "upload_public_image", fake_upload)


def _fake_http(monkeypatch, responses: dict) -> _FakeClient:
    client = _FakeClient(responses)
    monkeypatch.setattr(image_archive_service.httpx, "AsyncClient", lambda **kw: client)
    return client


@pytest.mark.asyncio
async def test_markdown_and_html_images_are_rewritten(monkeypatch) -> None:
    uploads: list = []
    _enable(monkeypatch, uploads)
    _fake_http(
        monkeypatch,
        {
            "https://site.example/a.png": _Response("image/png"),
            "https://cdn.example/b.jpg": _Response("image/jpeg"),
        },
    )

    content = (
        "Intro ![diagram](https://site.example/a.png) text\n"
        '<img class="x" src="https://cdn.example/b.jpg"> end'
    )
    result = await image_archive_service.archive_images(content)

    assert "https://site.example/a.png" not in result
    assert "https://cdn.example/b.jpg" not in result
    assert "https://media.example/1/image.png" in result
    assert "https://media.example/2/image.jpg" in result
    assert [u[1] for u in uploads] == ["image/png", "image/jpeg"]


@pytest.mark.asyncio
async def test_failed_image_keeps_its_hotlink(monkeypatch) -> None:
    uploads: list = []
    _enable(monkeypatch, uploads)
    _fake_http(
        monkeypatch,
        {
            "https://dead.example/x.png": httpx.ConnectError("refused"),
            "https://site.example/ok.png": _Response("image/png"),
        },
    )

    content = "![a](https://dead.example/x.png) ![b](https://site.example/ok.png)"
    result = await image_archive_service.archive_images(content)

    assert "https://dead.example/x.png" in result
    assert "https://site.example/ok.png" not in result
    assert len(uploads) == 1


@pytest.mark.asyncio
async def test_non_image_and_oversize_responses_are_skipped(monkeypatch) -> None:
    uploads: list = []
    _enable(monkeypatch, uploads)
    _fake_http(
        monkeypatch,
        {
            "https://site.example/page.html": _Response("text/html", b"<html>"),
            "https://site.example/huge.png": _Response(
                "image/png", b"x" * (image_archive_service.MAX_IMAGE_BYTES + 1)
            ),
        },
    )

    content = "![a](https://site.example/page.html) ![b](https://site.example/huge.png)"
    result = await image_archive_service.archive_images(content)

    assert result == content
    assert uploads == []


@pytest.mark.asyncio
async def test_image_count_is_capped(monkeypatch) -> None:
    uploads: list = []
    _enable(monkeypatch, uploads)
    urls = [f"https://site.example/{i}.png" for i in range(image_archive_service.MAX_IMAGES + 5)]
    client = _fake_http(monkeypatch, {u: _Response("image/png") for u in urls})

    content = " ".join(f"![i]({u})" for u in urls)
    await image_archive_service.archive_images(content)

    assert len(client.fetched) == image_archive_service.MAX_IMAGES


@pytest.mark.asyncio
async def test_duplicate_urls_archive_once(monkeypatch) -> None:
    uploads: list = []
    _enable(monkeypatch, uploads)
    client = _fake_http(monkeypatch, {"https://site.example/a.png": _Response("image/png")})

    content = "![a](https://site.example/a.png) ![again](https://site.example/a.png)"
    result = await image_archive_service.archive_images(content)

    assert len(client.fetched) == 1
    assert result.count("https://media.example/1/image.png") == 2


def test_disabled_without_public_bucket_config() -> None:
    assert image_archive_service.is_enabled() is False
