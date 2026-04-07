"""URL content scraper for bookmark import.

Handles three content types:
- Web articles → trafilatura extraction → markdown
- YouTube videos → transcript download → markdown
- PDF files → download + text extraction → markdown
- Everything else → title + URL reference page

Handles failures gracefully — returns None for URLs that can't be scraped.
"""

from __future__ import annotations

import io
import logging
import re
import time
from datetime import datetime

import httpx
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from .bookmark_parser import Bookmark

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; Boozle/1.0; +https://getboozle.com)"

_YOUTUBE_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
]


def _is_youtube(url: str) -> str | None:
    """Extract YouTube video ID from URL, or None if not YouTube."""
    for pat in _YOUTUBE_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def _is_pdf(url: str, content_type: str | None = None) -> bool:
    """Check if URL points to a PDF."""
    if content_type and "pdf" in content_type.lower():
        return True
    return url.lower().rstrip("/").endswith(".pdf")


# --- YouTube transcript ---


def _scrape_youtube(video_id: str) -> str | None:
    """Fetch YouTube transcript using youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.debug("youtube-transcript-api not installed, skipping transcript")
        return None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # Prefer manually created, fall back to auto-generated
        try:
            transcript = transcript_list.find_manually_created_transcript(["en"])
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(["en"])
            except Exception:
                # Try any available language
                transcript = next(iter(transcript_list))

        entries = transcript.fetch()
        lines = []
        for entry in entries:
            text = entry.get("text", entry) if isinstance(entry, dict) else str(entry)
            lines.append(str(text))
        return "\n\n".join(lines) if lines else None
    except Exception:
        return None


# --- PDF extraction ---


def _scrape_pdf(url: str, client: httpx.Client, timeout: float = 30.0) -> str | None:
    """Download a PDF and extract text content."""
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore[no-redef]
        except ImportError:
            logger.debug("pymupdf not installed, skipping PDF extraction")
            return None

    try:
        resp = client.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        pdf_bytes = resp.content

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                pages.append(text.strip())
        doc.close()

        return "\n\n---\n\n".join(pages) if pages else None
    except Exception:
        return None


# --- Web article extraction ---


def _scrape_article(url: str, client: httpx.Client, timeout: float = 15.0) -> str | None:
    """Fetch a web page and extract article content as markdown."""
    try:
        import trafilatura
    except ImportError:
        logger.debug("trafilatura not installed")
        return None

    try:
        resp = client.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        markdown = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            include_images=False,
            include_tables=True,
        )
        return markdown if markdown and len(markdown.strip()) > 50 else None
    except Exception:
        return None


# --- Main scraper ---


def scrape_url(url: str, client: httpx.Client, timeout: float = 15.0) -> tuple[str | None, str]:
    """Scrape a URL, auto-detecting content type.

    Returns (content_markdown, content_type) where content_type is
    "article", "youtube", "pdf", or "unknown".
    """
    # Check YouTube first (no need to fetch)
    video_id = _is_youtube(url)
    if video_id:
        content = _scrape_youtube(video_id)
        return content, "youtube"

    # Check if URL looks like a PDF
    if _is_pdf(url):
        content = _scrape_pdf(url, client, timeout=timeout)
        return content, "pdf"

    # Try HEAD request to check content-type before full download
    try:
        head = client.head(url, timeout=5, follow_redirects=True)
        ct = head.headers.get("content-type", "")
        if _is_pdf(url, ct):
            content = _scrape_pdf(url, client, timeout=timeout)
            return content, "pdf"
    except Exception:
        pass

    # Default: treat as web article
    content = _scrape_article(url, client, timeout=timeout)
    return content, "article"


def scrape_bookmarks(
    bookmarks: list[Bookmark],
    delay: float = 0.5,
    timeout: float = 15.0,
) -> dict[str, tuple[str | None, str]]:
    """Scrape a list of bookmarks sequentially with progress bar.

    Returns dict mapping URL to (content_markdown, content_type).
    """
    results: dict[str, tuple[str | None, str]] = {}

    with httpx.Client(
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            transient=False,
        ) as progress:
            task = progress.add_task("Scraping bookmarks...", total=len(bookmarks))

            for bookmark in bookmarks:
                url = bookmark.url
                if url in results:
                    progress.advance(task)
                    continue

                progress.update(task, description=f"[dim]{bookmark.title[:40]}...[/dim]")
                content, content_type = scrape_url(url, client, timeout=timeout)
                results[url] = (content, content_type)
                progress.advance(task)

                if delay > 0:
                    time.sleep(delay)

    return results


def format_page_content(bookmark: Bookmark, scraped: str | None, content_type: str = "article") -> str:
    """Format a bookmark as notebook page content."""
    date_str = ""
    if bookmark.add_date:
        try:
            date_str = f"\nBookmarked: {datetime.fromtimestamp(bookmark.add_date).strftime('%Y-%m-%d')}"
        except (ValueError, OSError):
            pass

    type_label = {"youtube": "YouTube Transcript", "pdf": "PDF", "article": "Web Article"}.get(content_type, "Link")

    if scraped:
        return (
            f"# {bookmark.title}\n\n"
            f"**Type:** {type_label}\n"
            f"**Source:** [{bookmark.url}]({bookmark.url}){date_str}\n\n"
            f"---\n\n{scraped}"
        )

    return (
        f"# {bookmark.title}\n\n"
        f"**Type:** {type_label}\n"
        f"[{bookmark.url}]({bookmark.url}){date_str}\n\n"
        f"Folder: {bookmark.folder_label}"
    )
