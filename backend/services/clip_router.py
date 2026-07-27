"""Route a URL-only clip to its handler.

All URL special-casing lives in SPECIAL_PAGES: pages whose real content
isn't in their HTML (YouTube transcripts, X threads) or whose URL is a
landing page for the actual artifact (arXiv abstract → paper PDF).
To add one, write a small class with `matches(url)` and `clip(row)` and
append an instance to SPECIAL_PAGES; to retire one, delete it.

Everything else is fetched and routed by content: PDF → file clip,
HTML → article page, anything else fails loud.
"""

import re
from urllib.parse import urlparse

import httpx

from ..integrations.x_saves import indexer as x_indexer
from . import clip_service, page_render_service, youtube_transcript
from .article_extraction import ArticleExtractionError

MAX_FETCH_BYTES = 20 * 1024 * 1024
FETCH_TIMEOUT = 30
USER_AGENT = "Stash/1.0 (+https://joinstash.ai)"


class UnsupportedUrlContent(Exception):
    """The URL resolved to content we can't clip."""


class YouTubeTranscriptPage:
    """YouTube watch pages have no extractable article — the transcript is
    the content."""

    _HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.hostname not in self._HOSTS:
            return False
        if parsed.hostname == "youtu.be":
            return bool(parsed.path.strip("/"))
        return parsed.path.startswith(("/watch", "/shorts"))

    async def clip(self, row: dict) -> dict:
        url = row["url"]
        video = await youtube_transcript.fetch_transcript(url)
        markdown = f"**{video['channel']}**\n\n{video['transcript']}"
        page = await clip_service.create_clip_page(
            owner_user_id=row["owner_user_id"],
            user_id=row["created_by"],
            url=url,
            name=video["title"],
            markdown=markdown,
            folder_id=row["folder_id"],
            kind=clip_service.KIND_VIDEO,
        )
        return {"page_id": page["id"]}


class XThreadPage:
    """x.com/twitter.com status pages are JS shells — the tweet (and its
    thread) comes from the twitterapi.io scraper instead."""

    _HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
    _STATUS_PATH = re.compile(r"^/(?:[^/]+)/status(?:es)?/(?P<id>\d+)")

    def matches(self, url: str) -> bool:
        return self._tweet_id(url) is not None

    def _tweet_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.hostname not in self._HOSTS:
            return None
        match = self._STATUS_PATH.match(parsed.path)
        return match.group("id") if match else None

    async def clip(self, row: dict) -> dict:
        url = row["url"]
        tweet = await x_indexer.fetch_tweet_markdown(self._tweet_id(url))
        page = await clip_service.create_clip_page(
            owner_user_id=row["owner_user_id"],
            user_id=row["created_by"],
            url=url,
            name=tweet["title"],
            markdown=tweet["markdown"],
            folder_id=row["folder_id"],
            kind=clip_service.KIND_TWEET,
        )
        return {"page_id": page["id"]}


class ArxivPdfPage:
    """arXiv abstract pages are landing pages — clip the paper PDF instead."""

    _ABS = re.compile(r"^https?://(?:www\.)?arxiv\.org/abs/(?P<paper>[^?#]+)")

    def matches(self, url: str) -> bool:
        return bool(self._ABS.match(url))

    async def clip(self, row: dict) -> dict:
        paper = self._ABS.match(row["url"]).group("paper")
        return await _fetch_and_save(row, f"https://arxiv.org/pdf/{paper}")


SPECIAL_PAGES = [YouTubeTranscriptPage(), XThreadPage(), ArxivPdfPage()]


def special_page_for(url: str):
    return next((h for h in SPECIAL_PAGES if h.matches(url)), None)


def is_special_page(url: str) -> bool:
    """URLs the clip endpoint must hand to the worker instead of extracting
    the posted DOM: the useful content isn't in the page HTML."""
    return special_page_for(url) is not None


async def process_url_import(row: dict) -> dict:
    """Fetch one url_imports row's content and create its page/file.

    Returns {"page_id": ...} or {"file_id": ...}; raises on any failure —
    the caller records the error on the row.
    """
    handler = special_page_for(row["url"])
    if handler:
        return await handler.clip(row)
    return await _fetch_and_save(row, row["url"])


async def _fetch_and_save(row: dict, fetch_url: str) -> dict:
    """The generic path: fetch the URL and route by content type."""
    owner_user_id = row["owner_user_id"]
    user_id = row["created_by"]
    url = row["url"]
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
        try:
            html = content.decode("utf-8", errors="replace")
            page = await clip_service.save_page_clip(
                owner_user_id=owner_user_id,
                user_id=user_id,
                url=url,
                html=html,
                title=row.get("title"),
                folder_id=row["folder_id"],
            )
        except ArticleExtractionError:
            # Escalation tier: the fetched HTML had no article — SPAs and
            # consent walls serve empty shells over HTTP. Render the page in
            # Chromium and extract from the settled DOM; a second extraction
            # failure is terminal (the caller saves the link-only bookmark).
            html = await page_render_service.render_page(url)
            page = await clip_service.save_page_clip(
                owner_user_id=owner_user_id,
                user_id=user_id,
                url=url,
                html=html,
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
