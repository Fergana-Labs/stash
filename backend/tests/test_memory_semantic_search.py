"""Tests for GET /me/sessions/events/semantic-search and the history-events
embedding backfill task (RUFU-126).

The semantic-search endpoint is the session-events counterpart of
/me/pages/semantic-search: same scope-membership auth, 503 while the
embedding service is unconfigured, 500 when the query cannot be embedded,
and similarity-ranked rows whose `similarity` is exposed as `rank` in the
HistoryEventListResponse envelope. The backfill task embeds history_events
rows that were written while no provider was configured (`embedding IS
NULL, embed_stale = FALSE`) — rows the 60s reconciler never retries — and
must be idempotent.
"""

import numpy as np
import pytest

from backend.services.embeddings import BaseEmbedder, set_embedder
from backend.tasks.embeddings import _backfill_history_events

from .conftest import unique_name

# Deterministic 384-dim basis vectors: e_i has 1.0 at index i, 0 elsewhere.
# Cosine similarity between different basis vectors is 0; a vector with
# itself is 1. Ordering is exact and independent of provider math.
DIMS = 384


def _basis(i: int) -> list[float]:
    v = [0.0] * DIMS
    v[i] = 1.0
    return v


class FixedVectorEmbedder(BaseEmbedder):
    """Configured fake that embeds every text as a fixed direction (e0)."""

    name = "fixed"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.batch_calls: list[list[str]] = []

    def is_configured(self) -> bool:
        return True

    async def embed_batch(self, texts: list[str]):
        self.batch_calls.append(list(texts))
        if self.fail:
            return None
        return [np.array(_basis(0), dtype=np.float32) for _ in texts]


class UnconfiguredEmbedder(BaseEmbedder):
    name = "unconfigured"

    def is_configured(self) -> bool:
        return False

    async def embed_batch(self, texts: list[str]):
        return None


async def _register(client) -> dict:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201, resp.body
    return resp.json()


async def _ensure_session(pool, owner_id, user_id, session_id: str):
    await pool.execute(
        "INSERT INTO sessions (id, owner_user_id, session_id, agent_name, created_by) "
        "VALUES (gen_random_uuid(), $1, $2, 'fusion', $3) "
        "ON CONFLICT (owner_user_id, session_id) DO NOTHING",
        owner_id,
        session_id,
        user_id,
    )


async def _insert_event(
    pool,
    owner_id,
    user_id,
    content: str,
    embedding: list[float] | None,
    session_id: str = "test-session",
):
    await _ensure_session(pool, owner_id, user_id, session_id)
    await pool.execute(
        "INSERT INTO history_events "
        "(id, owner_user_id, created_by, agent_name, event_type, session_id, "
        "content, metadata, embedding, content_hash, embed_stale) "
        "VALUES (gen_random_uuid(), $1, $2, 'fusion', 'assistant_message', "
        "$6, $3, $4, $5, NULL, FALSE)",
        owner_id,
        user_id,
        content,
        {},
        embedding,
        session_id,
    )


@pytest.mark.asyncio
async def test_semantic_search_requires_auth(client):
    resp = await client.get(
        "/api/v1/me/sessions/events/semantic-search", params={"q": "hello world"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_semantic_search_forbidden_outside_scope(client):
    alice = await _register(client)
    bob = await _register(client)
    resp = await client.get(
        "/api/v1/me/sessions/events/semantic-search",
        params={"q": "hello world"},
        headers={
            "Authorization": f"Bearer {bob['api_key']}",
            "X-Stash-Scope": alice["id"],
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_semantic_search_503_when_embedder_unconfigured(client):
    user = await _register(client)
    set_embedder(UnconfiguredEmbedder())
    resp = await client.get(
        "/api/v1/me/sessions/events/semantic-search",
        params={"q": "hello world"},
        headers={"Authorization": f"Bearer {user['api_key']}"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Embedding service not configured"


@pytest.mark.asyncio
async def test_semantic_search_500_on_embed_failure(client):
    user = await _register(client)
    set_embedder(FixedVectorEmbedder(fail=True))
    resp = await client.get(
        "/api/v1/me/sessions/events/semantic-search",
        params={"q": "hello world"},
        headers={"Authorization": f"Bearer {user['api_key']}"},
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to embed query"


@pytest.mark.asyncio
async def test_semantic_search_ranks_by_similarity(client, pool):
    user = await _register(client)
    set_embedder(FixedVectorEmbedder())  # query embeds as basis vector e0

    # Exact direction match (similarity 1.0) and orthogonal direction (0.0).
    await _insert_event(pool, user["id"], user["id"], "good match event", _basis(0))
    await _insert_event(pool, user["id"], user["id"], "other direction event", _basis(1))

    resp = await client.get(
        "/api/v1/me/sessions/events/semantic-search",
        params={"q": "hello world"},
        headers={"Authorization": f"Bearer {user['api_key']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_more"] is False
    events = body["events"]
    assert [e["content"] for e in events] == ["good match event", "other direction event"]
    assert events[0]["rank"] is not None
    assert events[0]["rank"] == pytest.approx(1.0, abs=1e-3)
    assert events[1]["rank"] == pytest.approx(0.0, abs=1e-3)
    # Session path metadata flows through the shared event model.
    assert events[0]["session_id"] == "test-session"


@pytest.mark.asyncio
async def test_semantic_search_scope_isolation(client, pool):
    alice = await _register(client)
    bob = await _register(client)
    set_embedder(FixedVectorEmbedder())

    await _insert_event(pool, alice["id"], alice["id"], "alice event", _basis(0))
    await _insert_event(pool, bob["id"], bob["id"], "bob event", _basis(0))

    resp = await client.get(
        "/api/v1/me/sessions/events/semantic-search",
        params={"q": "hello world"},
        headers={"Authorization": f"Bearer {alice['api_key']}"},
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert [e["content"] for e in events] == ["alice event"]

    resp = await client.get(
        "/api/v1/me/sessions/events/semantic-search",
        params={"q": "hello world"},
        headers={"Authorization": f"Bearer {bob['api_key']}"},
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert [e["content"] for e in events] == ["bob event"]


async def _db_state(pool, content: str) -> dict:
    row = await pool.fetchrow(
        "SELECT embedding, content_hash, embed_stale FROM history_events WHERE content = $1",
        content,
    )
    assert row is not None
    return {
        "embedded": row["embedding"] is not None,
        "content_hash": row["content_hash"],
        "embed_stale": row["embed_stale"],
    }


@pytest.mark.asyncio
async def test_backfill_embeds_unembedded_rows_and_is_idempotent(client, pool):
    user = await _register(client)
    user_id = user["id"]
    # Rows written while no provider was configured: NULL embedding, not stale.
    for i in range(3):
        await _insert_event(pool, user_id, user_id, f"backfill event {i}", None)

    embedder = FixedVectorEmbedder()
    set_embedder(embedder)
    embedded = await _backfill_history_events()
    assert embedded == 3
    assert len(embedder.batch_calls) == 1

    for i in range(3):
        state = await _db_state(pool, f"backfill event {i}")
        assert state["embedded"] is True
        assert state["content_hash"] is not None
        assert state["embed_stale"] is False

    # Second run: nothing left to backfill, no new provider calls.
    embedder2 = FixedVectorEmbedder()
    set_embedder(embedder2)
    embedded = await _backfill_history_events()
    assert embedded == 0
    assert len(embedder2.batch_calls) == 0


@pytest.mark.asyncio
async def test_backfill_hands_provider_failure_to_reconciler(client, pool):
    user = await _register(client)
    user_id = user["id"]
    for i in range(2):
        await _insert_event(pool, user_id, user_id, f"failure event {i}", None)

    # Provider failure: batch is handed to the 60s reconciler (embed_stale),
    # so a subsequent backfill run does not re-process or loop on it.
    set_embedder(FixedVectorEmbedder(fail=True))
    embedded = await _backfill_history_events()
    assert embedded == 0
    for i in range(2):
        state = await _db_state(pool, f"failure event {i}")
        assert state["embedded"] is False
        assert state["embed_stale"] is True

    embedder = FixedVectorEmbedder()
    set_embedder(embedder)
    embedded = await _backfill_history_events()
    assert embedded == 0
    assert len(embedder.batch_calls) == 0
