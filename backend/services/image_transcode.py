"""Image transcoding helpers.

HEIC (Apple's image format) is unsupported by every major browser except
Safari, so an `<img src=...>` to a HEIC file from R2 will silently fail
to render in Chrome/Firefox/Edge. We transcode HEIC → JPEG at upload
time so the file that lands in storage is something every browser knows
how to draw.
"""

import asyncio
import logging
from io import BytesIO
from pathlib import PurePosixPath

import pillow_heif
from PIL import Image

logger = logging.getLogger(__name__)

# Register libheif's HEIF/HEIC decoder with PIL.
pillow_heif.register_heif_opener()

# Quality 85 matches what most camera apps emit; visually lossless for
# photos while keeping files ~3x smaller than 95.
_JPEG_QUALITY = 85

_HEIC_MIME_TYPES = frozenset({"image/heic", "image/heif", "image/heic-sequence"})
_HEIC_EXTENSIONS = (".heic", ".heif", ".hif")


def is_heic(content_type: str, filename: str) -> bool:
    ct = (content_type or "").lower()
    if ct in _HEIC_MIME_TYPES:
        return True
    return filename.lower().endswith(_HEIC_EXTENSIONS)


def _transcode_heic_sync(content: bytes) -> bytes:
    img = Image.open(BytesIO(content))
    out = BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue()


async def maybe_transcode_heic(
    content: bytes,
    filename: str,
    content_type: str,
) -> tuple[bytes, str, str]:
    """Convert HEIC bytes to JPEG. Pass-through for non-HEIC inputs.

    Returns ``(content, filename, content_type)`` — for HEIC, the filename
    swaps its extension to ``.jpg`` and ``content_type`` becomes
    ``image/jpeg``. PIL decode is CPU-bound, so it runs on a worker
    thread to keep the event loop free.
    """
    if not is_heic(content_type, filename):
        return content, filename, content_type

    new_bytes = await asyncio.to_thread(_transcode_heic_sync, content)
    new_filename = PurePosixPath(filename).stem + ".jpg"
    logger.info(
        "transcoded HEIC upload %s (%d B) -> %s (%d B)",
        filename,
        len(content),
        new_filename,
        len(new_bytes),
    )
    return new_bytes, new_filename, "image/jpeg"
