"""PDF transcription via Claude vision, grounded by the embedded text layer.

pypdf reads a PDF's embedded text layer: exact characters, unreliable
layout — a three-column parts table comes out as one undifferentiated
stream. Claude vision reads the page images: reliable layout, but a
transcribed character can be wrong, and a misread digit in a part
number ships the wrong part. So each request carries both. The model
is instructed to take structure from the images and characters from
the text layer; a scanned PDF simply has no layer to attach and the
same call degrades to pure OCR.

Pages go up in chunks of PAGES_PER_REQUEST to the configured fast-tier
model (`ANTHROPIC_FAST_MODEL`), at most OCR_CONCURRENCY chunks in
flight at once, with vision capped at MAX_VISION_PAGES so one giant
catalog can't burn unbounded API spend. Pages past the cap contribute
their raw text layer under an explicit marker — the cap bounds spend,
it must not discard text that pypdf reads for free.

Chunk slices are built lazily, one per in-flight request: the whole
document held simultaneously as slices plus their base64 copies is what
used to breach the extraction child's RLIMIT_AS on scanned catalogs.

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
from .file_extraction import extract_text

MAX_VISION_PAGES = 100
PAGES_PER_REQUEST = 10
OCR_CONCURRENCY = 3
MAX_OUTPUT_TOKENS = 16000
# A dense 10-page catalog chunk emitting toward the 16K output cap routinely
# needs more than two minutes; at 120s the timeout burned all three extraction
# attempts on real customer catalogs.
REQUEST_TIMEOUT_SECONDS = 300.0

_PROMPT = (
    "Transcribe all text in this document exactly as it appears, in reading order. "
    "Output only the transcribed text - no commentary, no code fences. "
    "Preserve paragraph breaks. Render table rows as lines with cells separated by tabs. "
    "If a page contains no text, output nothing for it."
)

_LAYER_PROMPT = (
    "\n\nThe document's embedded text layer, extracted by machine, follows. Its characters "
    "are exact but its layout is unreliable. Trust it for characters - part numbers, digits, "
    "codes - and trust the page images for structure, column grouping, and reading order. "
    "Where the page renders a token visibly cut off - at a page edge, a clipped column, a "
    "cropped scan - the text layer usually holds the whole string: output the complete string "
    "from the text layer, never the truncated fragment you see in the image.\n\n"
    "<text_layer>\n{layer}\n</text_layer>"
)


def _slice_pdf(reader: pypdf.PdfReader, start: int, end: int) -> bytes:
    writer = pypdf.PdfWriter()
    for page in reader.pages[start:end]:
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _transcribe_chunk(client: AsyncAnthropic, chunk: bytes) -> str:
    layer = extract_text(chunk, "application/pdf")
    prompt = _PROMPT + (_LAYER_PROMPT.format(layer=layer) if layer else "")
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
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if response.stop_reason == "max_tokens":
        text += "\n\n[transcription truncated]"
    return text


def _text_layer_tail(reader: pypdf.PdfReader, start: int) -> str:
    """Text layer of pages[start:], read straight off the open reader —
    building a sliced copy of a several-hundred-page tail is itself enough
    to breach the extraction child's memory cap."""
    parts: list[str] = []
    for page in reader.pages[start:]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(p for p in parts if p).strip()


async def transcribe_pdf(content: bytes) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required to transcribe PDFs")

    reader = pypdf.PdfReader(io.BytesIO(content))
    total_pages = len(reader.pages)
    vision_pages = min(total_pages, MAX_VISION_PAGES)

    sem = asyncio.Semaphore(OCR_CONCURRENCY)

    async def transcribe_from(start: int) -> str:
        # The slice is built inside the semaphore and freed when this frame
        # ends, so peak memory is the document plus OCR_CONCURRENCY slices —
        # not the document plus every slice at once.
        async with sem:
            chunk = _slice_pdf(reader, start, min(start + PAGES_PER_REQUEST, vision_pages))
            return await _transcribe_chunk(client, chunk)

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        texts = await asyncio.gather(
            *(transcribe_from(start) for start in range(0, vision_pages, PAGES_PER_REQUEST))
        )
    finally:
        await client.close()

    parts = [t for t in texts if t]
    if total_pages > vision_pages:
        tail = _text_layer_tail(reader, vision_pages)
        if tail:
            parts.append(
                f"[vision transcription stopped at page {vision_pages} of {total_pages}; "
                "the rest is the embedded text layer, characters exact but layout flattened]"
            )
            parts.append(tail)
        else:
            parts.append(f"[transcription stopped at page {vision_pages} of {total_pages}]")
    return "\n\n".join(parts)
