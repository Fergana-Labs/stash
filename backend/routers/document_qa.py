"""Ask a question about one document, answered with vision.

The accommodation endpoint for text-only agent harnesses: the CLI sends the
document bytes and a question, Gemini looks at the pages server-side, and the
answer comes back as text. Vision-capable agents don't need this — they
download the document and read it with their own eyes.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from ..auth import get_current_user
from ..services import document_qa

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["document-qa"])

# Gemini's inline-data request limit is 20 MB; base64 inflates content by 4/3,
# so this is the largest document that fits in one request.
MAX_DOCUMENT_BYTES = 14 * 1024 * 1024

# Document types Gemini reads visually. Anything else has no pages to look at.
VISUAL_TYPES = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp")


@router.post("/ask-document")
async def ask_document(
    file: UploadFile,
    question: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    content_type = (file.content_type or "").lower()
    if content_type not in VISUAL_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"only PDFs and images can be asked about visually, not {content_type or 'unknown'}",
        )
    content = await file.read()
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"document exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB limit",
        )
    if not question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")

    try:
        answer = await document_qa.ask_document(content, content_type, question)
    except httpx.HTTPError as exc:
        # Provider trouble is the one failure normal operation should expect;
        # anything else (missing key, malformed response) is ours and stays a 500.
        logger.warning("ask-document provider error exception_type=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="the vision model call failed") from exc
    return {"answer": answer}
