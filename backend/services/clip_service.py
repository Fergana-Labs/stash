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


async def clips_subfolder_id(owner_user_id: UUID, user_id: UUID, name: str) -> UUID:
    """Idempotent Clips/<name> folder (e.g. Clips/YouTube)."""
    root_id = await clips_folder_id(owner_user_id, user_id)
    existing = await get_pool().fetchval(
        "SELECT id FROM folders WHERE owner_user_id = $1 AND parent_folder_id = $2 AND name = $3",
        owner_user_id,
        root_id,
        name,
    )
    if existing:
        return existing
    folder = await files_tree_service.create_folder(
        owner_user_id, name, user_id, parent_folder_id=root_id
    )
    return folder["id"]


async def ensure_clips_subtree(
    owner_user_id: UUID,
    user_id: UUID,
    root_name: str,
    paths: set[tuple[str, ...]],
) -> dict[tuple[str, ...], UUID]:
    """Idempotently create Clips/<root_name>/<path...> folders for every path.

    Returns path → folder id, with () mapping to Clips/<root_name>. Built for
    bulk imports: one lookup/create per distinct folder, not per bookmark.
    """
    pool = get_pool()
    root_id = await clips_subfolder_id(owner_user_id, user_id, root_name)
    folder_ids: dict[tuple[str, ...], UUID] = {(): root_id}

    async def ensure(path: tuple[str, ...]) -> UUID:
        if path in folder_ids:
            return folder_ids[path]
        parent_id = await ensure(path[:-1])
        name = path[-1]
        existing = await pool.fetchval(
            "SELECT id FROM folders WHERE owner_user_id = $1 AND parent_folder_id = $2 AND name = $3",
            owner_user_id,
            parent_id,
            name,
        )
        if existing:
            folder_ids[path] = existing
            return existing
        folder = await files_tree_service.create_folder(
            owner_user_id, name, user_id, parent_folder_id=parent_id
        )
        folder_ids[path] = folder["id"]
        return folder["id"]

    for path in paths:
        await ensure(path)
    return folder_ids


async def create_clip_page(
    *,
    owner_user_id: UUID,
    user_id: UUID,
    url: str,
    name: str,
    markdown: str,
    folder_id: UUID | None,
) -> dict:
    """Create the page every clip path ends in: source header + metadata,
    unique name, default folder Clips/."""
    clipped_at = datetime.now(UTC)
    # The source header keeps the URL inside the page body — full-text search
    # and the curator index page content, not metadata.
    content = f"> Clipped from <{url}> on {clipped_at.date().isoformat()}\n\n{markdown}"
    if folder_id is None:
        folder_id = await clips_folder_id(owner_user_id, user_id)
    return await files_tree_service.create_page_unique(
        owner_user_id,
        name,
        user_id,
        folder_id,
        content=content,
        metadata={"source_url": url, "clipped_at": clipped_at.isoformat()},
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
    article = extract_article(html, url)
    # The extractor's title beats the tab title (which carries "| Site" junk),
    # but non-article metadata sometimes lacks one.
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
):
    """Store a binary clip (PDF etc.) in Clips and stamp its source URL."""
    from ..routers.files import ingest_bytes

    if files_tree_service.detect_page_kind(filename, content_type) is not None:
        raise ValueError("Markdown/HTML clips must go through the page path")
    if folder_id is None:
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
