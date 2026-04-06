"""RAGFlow client: async HTTP client for RAGFlow document parsing and retrieval.

RAGFlow handles PDF parsing, OCR, chunking, and vector storage.
Configured via environment variables. Gracefully degrades when not configured.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RAGFLOW_API_URL = os.getenv("RAGFLOW_API_URL", "")
RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY", "")

_client: httpx.AsyncClient | None = None


def is_configured() -> bool:
    return bool(RAGFLOW_API_URL and RAGFLOW_API_KEY)


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=RAGFLOW_API_URL.rstrip("/"),
            timeout=60.0,
            headers={"Authorization": f"Bearer {RAGFLOW_API_KEY}"},
        )
    return _client


def _check(resp: dict) -> None:
    """Raise if RAGFlow returns a non-zero code."""
    if resp.get("code", -1) != 0:
        msg = resp.get("message", resp.get("data", "unknown error"))
        raise RuntimeError(f"RAGFlow error: {msg}")


async def create_dataset(name: str, description: str = "") -> str:
    """Create a RAGFlow dataset (knowledge base). Returns the dataset ID."""
    client = _get_client()
    resp = await client.post(
        "/api/v1/datasets",
        json={"name": name, "description": description},
    )
    resp.raise_for_status()
    body = resp.json()
    _check(body)
    return body["data"]["id"]


async def upload_document(dataset_id: str, filename: str, content: bytes) -> str:
    """Upload a file to a RAGFlow dataset. Returns the document ID."""
    client = _get_client()
    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/documents",
        files={"file": (filename, content)},
    )
    resp.raise_for_status()
    body = resp.json()
    _check(body)
    docs = body.get("data", [])
    if not docs:
        raise RuntimeError("RAGFlow upload returned no documents")
    return docs[0]["id"]


async def start_parsing(dataset_id: str, document_ids: list[str]) -> None:
    """Trigger parsing for uploaded documents."""
    client = _get_client()
    resp = await client.post(
        f"/api/v1/datasets/{dataset_id}/chunks",
        json={"document_ids": document_ids},
    )
    resp.raise_for_status()
    body = resp.json()
    _check(body)


async def get_document_status(dataset_id: str, doc_id: str) -> dict:
    """Get parsing status for a document. Returns {run, progress, progress_msg, chunk_count}."""
    client = _get_client()
    resp = await client.get(
        f"/api/v1/datasets/{dataset_id}/documents",
        params={"page": 1, "page_size": 100},
    )
    resp.raise_for_status()
    body = resp.json()
    _check(body)
    for doc in body.get("data", {}).get("docs", []):
        if doc["id"] == doc_id:
            return {
                "run": doc.get("run", "UNSTART"),
                "progress": doc.get("progress", 0),
                "progress_msg": doc.get("progress_msg", ""),
                "chunk_count": doc.get("chunk_count", 0),
            }
    raise RuntimeError(f"Document {doc_id} not found in dataset {dataset_id}")


async def search(
    dataset_ids: list[str],
    query: str,
    limit: int = 20,
    similarity_threshold: float = 0.2,
) -> list[dict]:
    """Search across RAGFlow datasets. Returns list of {content, doc_name, similarity}."""
    client = _get_client()
    resp = await client.post(
        "/api/v1/retrieval",
        json={
            "question": query,
            "dataset_ids": dataset_ids,
            "page": 1,
            "page_size": limit,
            "similarity_threshold": similarity_threshold,
            "vector_similarity_weight": 0.3,
            "top_k": 1024,
        },
    )
    resp.raise_for_status()
    body = resp.json()
    _check(body)
    chunks = body.get("data", {}).get("chunks", [])
    return [
        {
            "content": c.get("content", ""),
            "doc_name": c.get("document_keyword", ""),
            "doc_id": c.get("document_id", ""),
            "similarity": c.get("similarity", 0),
        }
        for c in chunks
    ]


async def delete_document(dataset_id: str, doc_id: str) -> None:
    """Delete a document from a RAGFlow dataset."""
    client = _get_client()
    resp = await client.request(
        "DELETE",
        f"/api/v1/datasets/{dataset_id}/documents",
        json={"ids": [doc_id]},
    )
    resp.raise_for_status()
    body = resp.json()
    _check(body)


async def delete_dataset(dataset_id: str) -> None:
    """Delete a RAGFlow dataset."""
    client = _get_client()
    resp = await client.request(
        "DELETE",
        "/api/v1/datasets",
        json={"ids": [dataset_id]},
    )
    resp.raise_for_status()
    body = resp.json()
    _check(body)


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
