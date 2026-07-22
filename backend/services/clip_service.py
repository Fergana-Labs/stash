"""Clips: user-initiated saves from the browser extension.

Every save produces two things:
  1. The raw clip — an HTML page (the readable article, images kept) or a
     binary file (PDF) — stored under the "Clips/raw" folder.
  2. A row in the "Bookmarks" table under "Clips" — the bookmark-manager
     index (title, URL, type, date, site, a link to the raw clip).

So "Clips" reads like a bookmark manager (the table) with the full captured
content one click away (the raw folder).
"""

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

from ..config import settings
from ..database import get_pool
from . import files_tree_service, image_archive_service, table_service
from .article_extraction import ArticleExtractionError, extract_article

CLIPS_FOLDER = "Clips"
RAW_FOLDER = "raw"
BOOKMARKS_TABLE = "Bookmarks"

# Clip types shown in the Bookmarks table's Type column.
KIND_PAGE = "Page"
KIND_PDF = "PDF"
KIND_VIDEO = "Video"
# A bookmark whose content could not be captured (login wall, no captions,
# unsupported content) — the link itself is still worth keeping.
KIND_LINK = "Link"

_BOOKMARK_COLUMNS = [
    {"name": "Title", "type": "text"},
    {"name": "URL", "type": "url"},
    {
        "name": "Type",
        "type": "select",
        "options": ["Page", "PDF", "Video", "Tweet", "Instagram", "Link"],
    },
    {"name": "Saved", "type": "text"},
    {"name": "Site", "type": "text"},
    {"name": "Clip", "type": "url"},
]


async def clips_folder_id(owner_user_id: UUID, user_id: UUID) -> UUID:
    folder = await files_tree_service.find_or_create_root_folder(
        owner_user_id, CLIPS_FOLDER, user_id
    )
    return folder["id"]


async def clips_subfolder_id(owner_user_id: UUID, user_id: UUID, name: str) -> UUID:
    """Idempotent Clips/<name> folder (e.g. Clips/raw)."""
    root_id = await clips_folder_id(owner_user_id, user_id)
    existing = await get_pool().fetchval(
        "SELECT id FROM folders WHERE owner_user_id = $1 AND parent_folder_id = $2 AND name = $3",
        owner_user_id,
        root_id,
        name,
    )
    if existing:
        return existing
    try:
        folder = await files_tree_service.create_folder(
            owner_user_id, name, user_id, parent_folder_id=root_id
        )
    except files_tree_service.DuplicateFolderName:
        # Lost a get-or-create race (concurrent batch saves): fetch the winner.
        return await get_pool().fetchval(
            "SELECT id FROM folders WHERE owner_user_id = $1 AND parent_folder_id = $2 AND name = $3",
            owner_user_id,
            root_id,
            name,
        )
    return folder["id"]


async def raw_folder_id(owner_user_id: UUID, user_id: UUID) -> UUID:
    """Where the actual clipped pages/files live: Clips/raw."""
    return await clips_subfolder_id(owner_user_id, user_id, RAW_FOLDER)


# --- Bookmarks table (the bookmark manager) -----------------------------------


# tables has no unique (owner, folder, name) index, so a lost get-or-create
# race would silently duplicate the Bookmarks table. This lock serializes
# lookups within the process — batch imports save many bookmarks concurrently.
_bookmarks_table_lock = asyncio.Lock()


async def _bookmarks_table(owner_user_id: UUID, user_id: UUID) -> tuple[UUID, dict[str, str]]:
    """Get-or-create the Bookmarks table in the Clips folder. Returns
    (table_id, {column name -> column id}) so callers can build row data."""
    clips_id = await clips_folder_id(owner_user_id, user_id)
    async with _bookmarks_table_lock:
        row = await get_pool().fetchrow(
            "SELECT id, columns FROM tables WHERE owner_user_id = $1 AND folder_id = $2 AND name = $3",
            owner_user_id,
            clips_id,
            BOOKMARKS_TABLE,
        )
        if row:
            return row["id"], {c["name"]: c["id"] for c in row["columns"]}
        table = await table_service.create_table(
            owner_user_id,
            BOOKMARKS_TABLE,
            "Everything you've saved with the Stash browser extension.",
            [dict(c) for c in _BOOKMARK_COLUMNS],
            user_id,
            folder_id=clips_id,
        )
        return table["id"], {c["name"]: c["id"] for c in table["columns"]}


def _clip_app_url(*, page_id: UUID | None = None, file_id: UUID | None = None) -> str:
    base = settings.PUBLIC_URL.rstrip("/")
    if page_id is not None:
        return f"{base}/p/{page_id}"
    return f"{base}/f/{file_id}"


def _site(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


async def add_bookmark(
    owner_user_id: UUID,
    user_id: UUID,
    *,
    title: str,
    url: str,
    kind: str,
    clip_url: str | None,
) -> None:
    """Append a row to the Bookmarks table for a saved clip. clip_url is None
    for link-only bookmarks (no captured content) — the url-typed Clip cell
    rejects empty strings, so the cell is omitted entirely."""
    table_id, cols = await _bookmarks_table(owner_user_id, user_id)
    data = {
        cols["Title"]: title,
        cols["URL"]: url,
        cols["Type"]: kind,
        cols["Saved"]: datetime.now(UTC).date().isoformat(),
        cols["Site"]: _site(url),
    }
    if clip_url is not None:
        data[cols["Clip"]] = clip_url
    await table_service.create_row(table_id, data, user_id)


async def save_link_only(
    owner_user_id: UUID,
    user_id: UUID,
    *,
    url: str,
    title: str | None,
) -> None:
    """Index a bookmark whose content hydration is done trying: no raw clip,
    just the Bookmarks-table row. The URL doubles as the title when the
    bookmark file didn't carry one."""
    await add_bookmark(
        owner_user_id,
        user_id,
        title=title or url,
        url=url,
        kind=KIND_LINK,
        clip_url=None,
    )


# --- Saving clips -------------------------------------------------------------


async def _create_raw_page(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    name: str,
    kind: str,
    content: str = "",
    content_html: str = "",
    folder_id: UUID | None,
) -> dict:
    """Create the clip page in Clips/raw and index it in the Bookmarks table."""
    if image_archive_service.is_enabled():
        if content:
            content = await image_archive_service.archive_images(content)
        if content_html:
            content_html = await image_archive_service.archive_images(content_html)
    clipped_at = datetime.now(UTC)
    metadata = {"source_url": url, "clipped_at": clipped_at.isoformat()}
    if folder_id is None:
        folder_id = await raw_folder_id(owner_user_id, user_id)
    page = await files_tree_service.create_page_unique(
        owner_user_id,
        name,
        user_id,
        folder_id,
        content=content,
        content_html=content_html,
        content_type="html" if content_html else "markdown",
        metadata=metadata,
    )
    await add_bookmark(
        owner_user_id,
        user_id,
        title=name,
        url=url,
        kind=kind,
        clip_url=_clip_app_url(page_id=page["id"]),
    )
    return page


async def store_html_clip(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    title: str,
    html: str,
) -> dict:
    """Store an already-readable article (Mozilla Readability output from the
    extension) as an HTML page with its images preserved, plus a bookmark."""
    if not title:
        raise ArticleExtractionError("The page has no usable title")
    # A one-line source note above the article keeps the URL in the body for
    # full-text search and the curator (which index page content, not metadata).
    header = (
        f'<p>Saved from <a href="{url}">{url}</a> on {datetime.now(UTC).date().isoformat()}</p>'
    )
    return await _create_raw_page(
        owner_user_id=owner_user_id,
        user_id=user_id,
        url=url,
        name=title,
        kind=KIND_PAGE,
        content_html=header + html,
        folder_id=None,
    )


async def create_clip_page(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    name: str,
    markdown: str,
    folder_id: UUID | None = None,
    kind: str = KIND_PAGE,
) -> dict:
    """Markdown clip (server-side extraction / transcripts) → page + bookmark."""
    content = f"> Saved from <{url}> on {datetime.now(UTC).date().isoformat()}\n\n{markdown}"
    return await _create_raw_page(
        owner_user_id=owner_user_id,
        user_id=user_id,
        url=url,
        name=name,
        kind=kind,
        content=content,
        folder_id=folder_id,
    )


async def save_page_clip(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    html: str,
    title: str | None,
    folder_id: UUID | None = None,
) -> dict:
    """Server-side path (URL/bookmark imports, no live DOM): extract the
    article and store it. The interactive clipper uses store_html_clip."""
    article = extract_article(html, url)
    name = article["title"] or title
    if not name:
        raise ArticleExtractionError("The page has no usable title")
    return await create_clip_page(
        owner_user_id=owner_user_id,
        user_id=user_id,
        url=url,
        name=name,
        markdown=article["markdown"],
        folder_id=folder_id,
    )


async def save_file_clip(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    filename: str,
    content: bytes,
    content_type: str,
    folder_id: UUID | None = None,
    kind: str = KIND_PDF,
):
    """Store a binary clip (PDF) in Clips/raw, record its source URL, and index
    it in the Bookmarks table."""
    from ..routers.files import ingest_bytes

    if files_tree_service.detect_page_kind(filename, content_type) is not None:
        raise ValueError("Markdown/HTML clips must go through the page path")
    if folder_id is None:
        folder_id = await raw_folder_id(owner_user_id, user_id)
    response = await ingest_bytes(
        owner_user_id=owner_user_id,
        user_id=user_id,
        filename=filename,
        content=content,
        content_type=content_type,
        folder_id=folder_id,
    )
    await get_pool().execute("UPDATE files SET source_url = $1 WHERE id = $2", url, response.id)
    await add_bookmark(
        owner_user_id,
        user_id,
        title=filename,
        url=url,
        kind=kind,
        clip_url=_clip_app_url(file_id=response.id),
    )
    return response
