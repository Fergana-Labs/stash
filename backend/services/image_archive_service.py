"""Archive a clip's images into the public media bucket.

Clipped articles hotlink their images to the source site, so clips rot
when the source dies. At save time each image reference (markdown or
<img> tag — a clip page stores one syntax or the other) is copied into
the public media bucket under a 128-bit random key and rewritten to the
stable public URL, making the clip self-contained.

A per-image failure keeps the original hotlink: an unreachable image must
never lose the article, and a hotlink is strictly better than a broken
reference. The whole pass is off (clips keep hotlinks, current behavior)
until S3_PUBLIC_BUCKET / S3_PUBLIC_BASE_URL are configured.
"""

import logging
import re
from urllib.parse import urlparse

import httpx

from . import storage_service

logger = logging.getLogger(__name__)

MAX_IMAGES = 20
MAX_IMAGE_BYTES = 10 * 1024 * 1024
FETCH_TIMEOUT = 20

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
_HTML_IMAGE = re.compile(r"<img[^>]+src=\"(https?://[^\"]+)\"", re.IGNORECASE)

# Map archived content types to a filename extension so the public URL
# stays recognizable as an image.
_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/svg+xml": "svg",
}


def is_enabled() -> bool:
    return storage_service.public_media_enabled()


async def archive_images(content: str) -> str:
    """Return `content` with every archivable image URL rewritten to its
    public archived copy. Failures leave that image's original URL."""
    urls: list[str] = []
    for pattern in (_MD_IMAGE, _HTML_IMAGE):
        for url in pattern.findall(content):
            if url not in urls:
                urls.append(url)
    if len(urls) > MAX_IMAGES:
        logger.info("archiving first %d of %d images", MAX_IMAGES, len(urls))
        urls = urls[:MAX_IMAGES]

    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        for url in urls:
            try:
                archived = await _archive_one(client, url)
            except Exception as exc:
                logger.warning(
                    "image archive failed host=%s exception_type=%s",
                    urlparse(url).netloc,
                    type(exc).__name__,
                )
                continue
            content = content.replace(url, archived)
    return content


async def _archive_one(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in _EXTENSIONS:
        raise ValueError(f"Not an archivable image: {content_type or 'unknown type'}")
    if len(response.content) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image larger than {MAX_IMAGE_BYTES} bytes")
    return await storage_service.upload_public_image(
        f"image.{_EXTENSIONS[content_type]}", response.content, content_type
    )
