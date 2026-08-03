"""Ask-document: vision answers for text-only agent harnesses.

The endpoint is the accommodation for agents whose tool loop flattens every
result to a string — the one way they can get a figure or table looked at.
These tests pin the boundary contract: only visual document types are
accepted, size stays inside the vision model's single-request limit, and an
empty question is rejected rather than billed.
"""

from httpx import AsyncClient

from backend.routers import document_qa as document_qa_router
from backend.tests.test_sources import _auth, _register


async def test_answers_a_question_about_a_pdf(client: AsyncClient, monkeypatch):
    api_key, _ = await _register(client)

    async def fake_ask(content, content_type, question):
        assert content == b"%PDF-1.4 tiny"
        assert content_type == "application/pdf"
        assert question == "does the 4515 have a hump?"
        return "Yes - the 4515 web rail shows a raised hump."

    monkeypatch.setattr(document_qa_router.document_qa, "ask_document", fake_ask)

    resp = await client.post(
        "/api/v1/ask-document",
        files={"file": ("guide.pdf", b"%PDF-1.4 tiny", "application/pdf")},
        data={"question": "does the 4515 have a hump?"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Yes - the 4515 web rail shows a raised hump."


async def test_non_visual_types_are_refused(client: AsyncClient):
    """A text file has nothing to look at — refusing beats paying for a vision
    call that reads plain text worse than the caller already can."""
    api_key, _ = await _register(client)

    resp = await client.post(
        "/api/v1/ask-document",
        files={"file": ("notes.txt", b"just text", "text/plain")},
        data={"question": "what does it say?"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 415


async def test_oversize_document_is_413(client: AsyncClient, monkeypatch):
    api_key, _ = await _register(client)
    monkeypatch.setattr(document_qa_router, "MAX_DOCUMENT_BYTES", 10)

    resp = await client.post(
        "/api/v1/ask-document",
        files={"file": ("big.pdf", b"%PDF-1.4 more than ten bytes", "application/pdf")},
        data={"question": "anything"},
        headers=_auth(api_key),
    )
    assert resp.status_code == 413


async def test_blank_question_is_rejected(client: AsyncClient):
    api_key, _ = await _register(client)

    resp = await client.post(
        "/api/v1/ask-document",
        files={"file": ("guide.pdf", b"%PDF-1.4 tiny", "application/pdf")},
        data={"question": "   "},
        headers=_auth(api_key),
    )
    assert resp.status_code == 422
