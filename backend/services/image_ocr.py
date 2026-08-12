"""Image transcription via Gemini vision.

A screenshot is the most common thing a person drops into their stash and the
one thing an agent could never read: `file_extraction.extract_text` has no
branch for images, so every PNG landed with an empty knowledge-base entry.
This module gives an image the same treatment `pdf_ocr` gives a scan — text
transcribed character-for-character, and everything non-textual described in
place so a reader who cannot see it still gets the information.

Only the formats Gemini accepts inline are transcribable; anything else (SVG,
TIFF, …) returns "" and stores no text, the same declared-support stance
`extract_text` takes. Like `pdf_ocr`, it raises on failure so the extraction
pipeline's retry machinery records the error rather than silently storing an
empty entry.
"""

from __future__ import annotations

import base64

import httpx

from ..config import settings

TRANSCRIBABLE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/heic", "image/heif")
MAX_OUTPUT_TOKENS = 8000
REQUEST_TIMEOUT_SECONDS = 120.0

_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_PROMPT = (
    "Describe this image so that someone who cannot see it gets everything it conveys. "
    "Output only the description - no commentary, no surrounding code fence. "
    "Transcribe every piece of visible text exactly as printed, in reading order, "
    "character-for-character - names, numbers, codes, labels, UI text, handwriting. "
    "Render any table as a markdown table. "
    "Then state what the image shows: its subject, the setting, and every identifying "
    "detail (people and what they are doing, objects, shapes, colors, charts and their "
    "values, diagram structure and callouts). "
    "If it is a screenshot, say what application or page it shows and what state it is in."
)


async def transcribe_image(content: bytes, content_type: str) -> str:
    if content_type not in TRANSCRIBABLE_TYPES:
        return ""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required to transcribe images")

    async with httpx.AsyncClient(
        headers={"x-goog-api-key": settings.GEMINI_API_KEY},
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        response = await client.post(
            _GENERATE_URL.format(model=settings.GEMINI_EXTRACTION_MODEL),
            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": content_type,
                                    "data": base64.standard_b64encode(content).decode("ascii"),
                                }
                            },
                            {"text": _PROMPT},
                        ]
                    }
                ],
                "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS, "temperature": 0},
            },
        )
    response.raise_for_status()
    candidates = response.json().get("candidates")
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if candidates[0].get("finishReason") == "MAX_TOKENS":
        text += "\n\n[transcription truncated]"
    return text
