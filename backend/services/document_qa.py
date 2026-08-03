"""Answer a question about a document with vision — eyes for text-only agents.

Most agents connected to Stash have vision-capable harnesses: they download a
PDF and read it themselves. Agents whose tool loop is text-only end-to-end
(every tool result flattened to a string) can never see a page no matter how
the bytes reach them. This service is their accommodation: the question comes
in as text, Gemini looks at the actual document, and the answer goes back as
text — so a figure's content is available on demand, conditioned on the real
question instead of whatever a precomputed description happened to keep.

One document, one call: no chunking. The request cap in the router keeps the
document inside Gemini's inline-data limit, and a question about a specific
figure or table doesn't need a whole-catalog sweep.
"""

from __future__ import annotations

import base64

import httpx

from ..config import settings

MAX_OUTPUT_TOKENS = 4000
REQUEST_TIMEOUT_SECONDS = 120.0

_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_PROMPT = (
    "Answer the question using only what this document shows. Look at figures, "
    "photos, diagrams, and tables directly - visual details (shapes, labels, "
    "colors, callouts, table cell pairings) are usually the point of the question. "
    "Transcribe part numbers, codes, and digits exactly as printed. If the "
    "document does not contain the answer, say so plainly.\n\n"
    "Question: {question}"
)


async def ask_document(content: bytes, content_type: str, question: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required to answer document questions")

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
                            {"text": _PROMPT.format(question=question)},
                        ]
                    }
                ],
                "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
            },
        )
    response.raise_for_status()
    candidates = response.json().get("candidates")
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
