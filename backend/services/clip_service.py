"""Clips: user-initiated saves from the browser extension.

A clip is an ordinary page or file in the "Clips" root folder — the
extension is just another upload client. Web pages go through the shared
article extractor and become markdown pages; PDFs and other binaries become
S3-backed file rows with their source URL recorded.
"""

from datetime import UTC, datetime
from uuid import UUID

from ..database import get_pool
from . import files_tree_service
from .article_extraction import ArticleExtractionError, extract_article

CLIPS_FOLDER = "Clips"


async def clips_folder_id(owner_user_id: UUID, user_id: UUID) -> UUID:
    folder = await files_tree_service.find_or_create_root_folder(
        owner_user_id, CLIPS_FOLDER, user_id
    )
    return folder["id"]


async def save_page_clip(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    html: str,
    title: str | None,
) -> dict:
    article = extract_article(html, url)
    # The extractor's title beats the tab title (which carries "| Site" junk),
    # but non-article metadata sometimes lacks one.
    name = article["title"] or title
    if not name:
        raise ArticleExtractionError("The page has no usable title")
    clipped_at = datetime.now(UTC)
    # The source header keeps the URL inside the page body — full-text search
    # and the curator index page content, not metadata.
    content = f"> Clipped from <{url}> on {clipped_at.date().isoformat()}\n\n{article['markdown']}"
    folder_id = await clips_folder_id(owner_user_id, user_id)
    return await files_tree_service.create_page_unique(
        owner_user_id,
        name,
        user_id,
        folder_id,
        content=content,
        metadata={"source_url": url, "clipped_at": clipped_at.isoformat()},
    )


async def save_file_clip(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    filename: str,
    content: bytes,
    content_type: str,
):
    """Store a binary clip (PDF etc.) in Clips and stamp its source URL."""
    from ..routers.files import ingest_bytes

    if files_tree_service.detect_page_kind(filename, content_type) is not None:
        raise ValueError("Markdown/HTML clips must go through the page path")
    folder_id = await clips_folder_id(owner_user_id, user_id)
    response = await ingest_bytes(
        owner_user_id=owner_user_id,
        user_id=user_id,
        filename=filename,
        content=content,
        content_type=content_type,
        folder_id=folder_id,
    )
    await get_pool().execute("UPDATE files SET source_url = $1 WHERE id = $2", url, response.id)
    return response
