"""Best-effort text extraction for uploaded files.

Supported:
- PDFs with embedded text → pypdf (pure Python).
- Plain-text / JSON / XML → UTF-8 decode.
- Everything else → None.

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
    """Make `text` safe for a Postgres TEXT column.

    Two hazards seen in the wild from pypdf output:
    - null bytes (0x00) — Postgres rejects them outright.
    - unpaired UTF-16 surrogates (U+D800..U+DFFF) — asyncpg can't encode
      them to UTF-8 on the wire. Happens when a PDF's CMap maps a
      character to one half of a surrogate pair without the other.

    Both are stripped. The encode/decode round-trip with
    `errors="replace"` is cheap and handles any other exotic codepoints
    that slip past the surrogate check.
    """
    if "\x00" in text:
        text = text.replace("\x00", "")
    # Drop unpaired surrogates by round-tripping via UTF-8 with replacement.
    text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
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
