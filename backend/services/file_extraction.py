"""Best-effort text extraction for uploaded files.

Lightweight by design — **no OCR, no image rasterization**. We keep:

- PDFs with embedded text → pypdf (pure Python, no numpy/BLAS).
- Plain-text / JSON / XML → UTF-8 decode.
- Everything else (images, scanned PDFs, binary formats) → None.

OCR was dropped after scanned-PDF/image paths OOM'd the Render Starter
dyno (numpy/OpenBLAS reserves ~200 MB at import time, before any work,
pushing the extraction child past RLIMIT_AS before pypdf could run). If
we bring OCR back, it belongs in a dedicated worker service with more
RAM — not in the same process as pypdf.

`extract_text` never raises. Every failure returns None so uploads
always succeed even if the file is corrupt or the libs aren't present.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

try:
    import pypdf  # type: ignore

    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False


def _extract_pdf_embedded(content: bytes) -> str:
    if not _HAS_PYPDF:
        return ""
    reader = pypdf.PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(p for p in parts if p).strip()


def _sanitize_for_postgres(text: str) -> str:
    """Postgres TEXT columns reject null bytes (0x00). Some PDFs emit them
    from odd CMap entries; strip so the UPDATE doesn't fail."""
    if "\x00" in text:
        return text.replace("\x00", "")
    return text


def extract_text(content: bytes, content_type: str) -> str | None:
    """Return extracted text, or None when extraction is not possible/failed.

    Never raises — caller can trust this to not break the upload path.
    """
    try:
        ct = (content_type or "").lower()

        if ct == "application/pdf" or ct.endswith("/pdf"):
            text = _extract_pdf_embedded(content)
            return _sanitize_for_postgres(text) if text else None

        if ct.startswith("text/") or ct in ("application/json", "application/xml"):
            return _sanitize_for_postgres(content.decode("utf-8", errors="replace"))

        return None
    except Exception:
        logger.exception("file_extraction: extract_text failed for %s", content_type)
        return None
