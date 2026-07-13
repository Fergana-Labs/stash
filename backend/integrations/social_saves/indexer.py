"""Hydrate Instagram saves via ScrapeCreators.

Skeleton rows arrive from the extension push (see routers/sources.py
saved_items_router). Each sync pass fills a bounded batch: post details
and reel transcript from ScrapeCreators (public data, product-level key),
plus the media bytes themselves into object storage — the point of a
commonplace book is that a save survives the post being deleted or the
account going private. Per-item failures land on the row, loudly; rows
are never deleted by sync (archive semantics).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx

from ...config import settings
from ...database import get_pool
from ...services import source_service, storage_service

logger = logging.getLogger(__name__)

SC_POST_URL = "https://api.scrapecreators.com/v1/instagram/post"
SC_TRANSCRIPT_URL = "https://api.scrapecreators.com/v2/instagram/media/transcript"

# The transcript endpoint transcribes on demand (10-30s per reel).
SC_TIMEOUT = 90
MAX_MEDIA_BYTES = 50 * 1024 * 1024
HYDRATION_BATCH = 25
MAX_HYDRATION_ATTEMPTS = 3


def post_url(shortcode: str) -> str:
    return f"https://www.instagram.com/p/{shortcode}/"


async def index_instagram_saves(source: dict) -> str | None:
    if not settings.SCRAPECREATORS_API_KEY:
        raise RuntimeError("SCRAPECREATORS_API_KEY is not set")
    if not storage_service.is_configured():
        raise RuntimeError("File storage is not configured; cannot archive save media")

    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT id, path FROM instagram_save_docs
        WHERE source_id = $1 AND (
              hydration_status = 'pending'
           OR (hydration_status = 'failed' AND hydration_attempts < {MAX_HYDRATION_ATTEMPTS})
        )
        ORDER BY created_at
        LIMIT {HYDRATION_BATCH}
        """,
        source_id,
    )

    async with httpx.AsyncClient(
        timeout=SC_TIMEOUT, headers={"x-api-key": settings.SCRAPECREATORS_API_KEY}
    ) as client:
        for row in rows:
            try:
                await _hydrate_one(client, source_id, owner_user_id, row["path"])
            except Exception as exc:
                logger.warning(
                    "instagram save hydration failed source=%s path=%s exception_type=%s",
                    source_id,
                    row["path"],
                    type(exc).__name__,
                )
                await pool.execute(
                    "UPDATE instagram_save_docs SET hydration_status = 'failed', "
                    "hydration_error = $3, hydration_attempts = hydration_attempts + 1, "
                    "updated_at = now() WHERE source_id = $1 AND path = $2",
                    source_id,
                    row["path"],
                    f"{type(exc).__name__}: {exc}"[:2000],
                )
    return None


async def _hydrate_one(
    client: httpx.AsyncClient, source_id: UUID, owner_user_id: UUID, shortcode: str
) -> None:
    url = post_url(shortcode)
    post = await _fetch_post(client, url)

    transcript = ""
    if post["is_video"]:
        transcript = await _fetch_transcript(client, url)

    media_key, media_content_type = await _archive_media(owner_user_id, shortcode, post)

    posted = post["posted_at"]
    parts = [
        f"# @{post['username']} — Instagram save",
        f"Posted: {posted.isoformat()}",
        f"URL: {url}",
    ]
    if post["caption"]:
        quoted = "\n".join(f"> {line}" for line in post["caption"].splitlines())
        parts.append(f"\n{quoted}")
    if transcript:
        parts.append(f"\n## Transcript\n\n{transcript}")
    content = "\n".join(parts)

    await source_service.upsert_content_document(
        table="instagram_save_docs",
        source_id=source_id,
        owner_user_id=owner_user_id,
        path=shortcode,
        name=f"@{post['username']} - {posted.date().isoformat()}",
        kind="post",
        content=content,
        external_ref=shortcode,
        external_updated_at=posted,
    )
    await get_pool().execute(
        "UPDATE instagram_save_docs SET media_storage_key = $3, media_content_type = $4, "
        "hydration_status = 'done', hydration_error = NULL, updated_at = now() "
        "WHERE source_id = $1 AND path = $2",
        source_id,
        shortcode,
        media_key,
        media_content_type,
    )


async def _fetch_post(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(SC_POST_URL, params={"url": url})
    response.raise_for_status()
    media = response.json()["data"]["xdt_shortcode_media"]
    caption_edges = (media.get("edge_media_to_caption") or {}).get("edges") or []
    caption = caption_edges[0]["node"]["text"] if caption_edges else ""
    return {
        "username": media["owner"]["username"],
        "caption": caption,
        "posted_at": datetime.fromtimestamp(media["taken_at_timestamp"], UTC),
        "is_video": bool(media.get("is_video")),
        "media_url": media.get("video_url") or media.get("display_url"),
    }


async def _fetch_transcript(client: httpx.AsyncClient, url: str) -> str:
    """The reel's speech, or "" when ScrapeCreators detects none (silent
    reels and videos over their 2-minute limit report success=false)."""
    response = await client.get(SC_TRANSCRIPT_URL, params={"url": url})
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        return ""
    return " ".join(t["text"] for t in (payload.get("transcripts") or []) if t.get("text")).strip()


async def _archive_media(owner_user_id: UUID, shortcode: str, post: dict) -> tuple[str, str]:
    """Download the post's video/image from Instagram's CDN (the signed URL
    ScrapeCreators just returned is fresh) into object storage."""
    media_url = post["media_url"]
    if not media_url:
        raise ValueError("Post has no media URL")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as media_client:
        response = await media_client.get(media_url)
        response.raise_for_status()
        content = response.content
        if len(content) > MAX_MEDIA_BYTES:
            raise ValueError(f"Media larger than {MAX_MEDIA_BYTES} bytes")
        content_type = response.headers.get(
            "content-type", "video/mp4" if post["is_video"] else "image/jpeg"
        )
    extension = "mp4" if post["is_video"] else "jpg"
    storage_key = await storage_service.upload_file(
        str(owner_user_id),
        f"instagram-{shortcode}.{extension}",
        content,
        content_type,
    )
    return storage_key, content_type
