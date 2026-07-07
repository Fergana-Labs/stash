"""OCR for scanned PDFs via Claude vision.

A scanned PDF has no embedded text layer, so pypdf yields nothing.
This module sends the PDF itself to the configured fast-tier model
(`ANTHROPIC_FAST_MODEL`), which reads the page images and transcribes
them. Pages go up in chunks of PAGES_PER_REQUEST, all chunks in
parallel, capped at MAX_OCR_PAGES so one giant scan can't burn
unbounded API spend.

Unlike `file_extraction.extract_text`, this module raises on failure
(missing API key, API errors) so the extraction pipeline's retry
machinery records the error and retries instead of silently storing
an empty knowledge-base entry.
"""

from __future__ import annotations

import asyncio
import base64
import io

import pypdf
from anthropic import AsyncAnthropic

from ..config import settings

MAX_OCR_PAGES = 100
PAGES_PER_REQUEST = 10
MAX_OUTPUT_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 120.0

_PROMPT = (
    "Transcribe all text in this scanned document exactly as it appears, in reading order. "
    "Output only the transcribed text - no commentary, no code fences. "
    "Preserve paragraph breaks. Render table rows as lines with cells separated by tabs. "
    "If a page contains no text, output nothing for it."
)


def _slice_pdf(reader: pypdf.PdfReader, start: int, end: int) -> bytes:
    writer = pypdf.PdfWriter()
    for page in reader.pages[start:end]:
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _ocr_chunk(client: AsyncAnthropic, chunk: bytes) -> str:
    response = await client.messages.create(
        model=settings.ANTHROPIC_FAST_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.standard_b64encode(chunk).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if response.stop_reason == "max_tokens":
        text += "\n\n[transcription truncated]"
    return text


async def ocr_pdf(content: bytes) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required to OCR scanned PDFs")

    reader = pypdf.PdfReader(io.BytesIO(content))
    total_pages = len(reader.pages)
    ocr_pages = min(total_pages, MAX_OCR_PAGES)
    chunks = [
        _slice_pdf(reader, start, min(start + PAGES_PER_REQUEST, ocr_pages))
        for start in range(0, ocr_pages, PAGES_PER_REQUEST)
    ]

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        texts = await asyncio.gather(*(_ocr_chunk(client, chunk) for chunk in chunks))
    finally:
        await client.close()

    parts = [t for t in texts if t]
    if total_pages > MAX_OCR_PAGES:
        parts.append(f"[OCR stopped at page {MAX_OCR_PAGES} of {total_pages}]")
    return "\n\n".join(parts)
