"""Route a URL-only clip to its handler.

All URL special-casing lives here — the extension and importers just send
URLs. YouTube watch pages have no extractable article (the transcript is
the content) and arXiv abstract pages are landing pages for the actual
paper, so both get dedicated handling before the generic fetch. Everything
else is fetched and routed by content: PDF → file clip, HTML → article
page, anything else fails loud.
"""

import asyncio
import re
from urllib.parse import urlparse

import httpx

from . import clip_service, youtube_transcript

MAX_FETCH_BYTES = 20 * 1024 * 1024
FETCH_TIMEOUT = 30
USER_AGENT = "Stash/1.0 (+https://joinstash.ai)"

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_ARXIV_ABS = re.compile(r"^https?://(?:www\.)?arxiv\.org/abs/(?P<paper>[^?#]+)")


class UnsupportedUrlContent(Exception):
    """The URL resolved to content we can't clip."""


def is_youtube(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.hostname not in _YOUTUBE_HOSTS:
        return False
    if parsed.hostname == "youtu.be":
        return bool(parsed.path.strip("/"))
    return parsed.path.startswith(("/watch", "/shorts"))


def normalize_arxiv(url: str) -> str:
    """arXiv abstract pages are landing pages — clip the paper PDF instead."""
    match = _ARXIV_ABS.match(url)
    if match:
        return f"https://arxiv.org/pdf/{match.group('paper')}"
    return url


def is_async_url(url: str) -> bool:
    """URLs the clip endpoint must hand to the worker instead of extracting
    the posted DOM: the useful content isn't in the page HTML."""
    return is_youtube(url) or bool(_ARXIV_ABS.match(url))


async def process_url_import(row: dict) -> dict:
    """Fetch one url_imports row's content and create its page/file.

    Returns {"page_id": ...} or {"file_id": ...}; raises on any failure —
    the caller records the error on the row.
    """
    owner_user_id = row["owner_user_id"]
    user_id = row["created_by"]
    url = row["url"]

    if is_youtube(url):
        video = await asyncio.to_thread(youtube_transcript.fetch_transcript, url)
        markdown = f"**{video['channel']}**\n\n{video['transcript']}"
        page = await clip_service.create_clip_page(
            owner_user_id=owner_user_id,
            user_id=user_id,
            url=url,
            name=video["title"],
            markdown=markdown,
            folder_id=row["folder_id"],
            kind=clip_service.KIND_VIDEO,
        )
        return {"page_id": page["id"]}

    fetch_url = normalize_arxiv(url)
    content, content_type = await _fetch(fetch_url)

    if "application/pdf" in content_type or content[:5] == b"%PDF-":
        filename = urlparse(fetch_url).path.rsplit("/", 1)[-1] or "clip"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        response = await clip_service.save_file_clip(
            owner_user_id=owner_user_id,
            user_id=user_id,
            url=url,
            filename=filename,
            content=content,
            content_type="application/pdf",
            folder_id=row["folder_id"],
        )
        return {"file_id": response.id}

    if "text/html" in content_type or content.lstrip()[:1] == b"<":
        page = await clip_service.save_page_clip(
            owner_user_id=owner_user_id,
            user_id=user_id,
            url=url,
            html=content.decode("utf-8", errors="replace"),
            title=row.get("title"),
            folder_id=row["folder_id"],
        )
        return {"page_id": page["id"]}

    raise UnsupportedUrlContent(f"Unsupported content type: {content_type or 'unknown'}")


async def _fetch(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_FETCH_BYTES:
                    raise UnsupportedUrlContent("Response larger than 20 MB")
                chunks.append(chunk)
            return b"".join(chunks), content_type
