"""Best-effort text extraction for uploaded files.

Zero external API dependencies:
- PDFs with embedded text → pypdf (pure Python).
- Plain-text / JSON → UTF-8 decode.
- Images and scanned PDFs → pytesseract + pypdfium2, only when the
  `tesseract` binary is installed on the host. Absent → silently skip.

`extract_text` never raises. Every failure returns None so uploads
always succeed even if the file is corrupt or the libs aren't present.
"""

from __future__ import annotations

import io
import logging
import shutil

logger = logging.getLogger(__name__)


_HAS_TESSERACT = shutil.which("tesseract") is not None

try:
    import pypdf  # type: ignore

    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False

try:
    import pypdfium2  # type: ignore

    _HAS_PYPDFIUM2 = True
except ImportError:
    _HAS_PYPDFIUM2 = False

try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    _HAS_OCR_LIBS = True
except ImportError:
    _HAS_OCR_LIBS = False


_OCR_AVAILABLE = _HAS_TESSERACT and _HAS_OCR_LIBS


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


def _ocr_image_bytes(content: bytes) -> str:
    image = Image.open(io.BytesIO(content))
    return (pytesseract.image_to_string(image) or "").strip()


def _ocr_pdf(content: bytes) -> str:
    if not (_HAS_PYPDFIUM2 and _OCR_AVAILABLE):
        return ""
    pdf = pypdfium2.PdfDocument(content)
    parts: list[str] = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                pil_image = page.render(scale=2).to_pil()
                text = pytesseract.image_to_string(pil_image) or ""
                if text.strip():
                    parts.append(text)
            finally:
                page.close()
    finally:
        pdf.close()
    return "\n\n".join(parts).strip()


def extract_text(content: bytes, content_type: str) -> str | None:
    """Return extracted text, or None when extraction is not possible/failed.

    Never raises — caller can trust this to not break the upload path.
    """
    try:
        ct = (content_type or "").lower()

        if ct == "application/pdf" or ct.endswith("/pdf"):
            text = _extract_pdf_embedded(content)
            if text:
                return text
            # Digital extraction empty — try OCR on rasterized pages.
            if _OCR_AVAILABLE:
                return _ocr_pdf(content) or None
            return None

        if ct.startswith("image/"):
            if _OCR_AVAILABLE:
                return _ocr_image_bytes(content) or None
            return None

        if ct.startswith("text/") or ct in ("application/json", "application/xml"):
            return content.decode("utf-8", errors="replace")

        return None
    except Exception:
        logger.exception("file_extraction: extract_text failed for %s", content_type)
        return None


def ocr_available() -> bool:
    """Expose OCR availability so callers/tests can branch if needed."""
    return _OCR_AVAILABLE
