"""Images reach the knowledge base via vision, or not at all.

No parser reads pixels, so a stored image with no transcription is a hole in
the stash the user can see but the agent cannot. These tests pin the two edges
of that: a format Gemini cannot take inline stores nothing rather than
pretending, and a missing key fails loud so the retry machinery records it
instead of persisting an empty entry.
"""

import pytest

from backend.config import settings
from backend.services import image_ocr


@pytest.mark.asyncio
async def test_format_gemini_cannot_read_stores_nothing(monkeypatch) -> None:
    async def fail(*args, **kwargs):
        raise AssertionError("no API call for an untranscribable format")

    monkeypatch.setattr(image_ocr.httpx.AsyncClient, "post", fail)

    assert await image_ocr.transcribe_image(b"<svg/>", "image/svg+xml") == ""


@pytest.mark.asyncio
async def test_missing_api_key_fails_loud(monkeypatch) -> None:
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await image_ocr.transcribe_image(b"\x89PNG....", "image/png")
