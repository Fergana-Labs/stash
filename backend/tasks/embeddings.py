"""Embedding reconciliation task.

Replaces `workers/embedding_reconciler.py`. Beat-scheduled (every 60s
in `celery_app.py`).

Periodic batch reconciliation of rows where `embed_stale = TRUE`:
pages, table_rows, history_events. Same queries as the original
worker — only the loop has moved from in-process asyncio to Celery Beat.
"""

from __future__ import annotations

import hashlib
import logging

from ..celery_app import celery
from ..database import get_pool
from ..services import embeddings as embedding_service
from ..services.table_service import _build_embedding_text
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

BATCH_SIZE = 32


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _reconcile_pages() -> int:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, content_markdown FROM pages "
        "WHERE embed_stale AND deleted_at IS NULL LIMIT $1",
        BATCH_SIZE,
    )
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    texts = [r["content_markdown"] or "" for r in rows]
    vecs = await embedding_service.embed_batch(texts)
    if not vecs:
        return 0
    await pool.executemany(
        "UPDATE pages SET embedding = $1, embed_stale = FALSE WHERE id = $2",
        list(zip(vecs, ids)),
    )
    return len(ids)


async def _reconcile_table_rows() -> int:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT tr.id, tr.data, tr.table_id, t.columns, t.embedding_config "
        "FROM table_rows tr JOIN tables t ON t.id = tr.table_id "
        "WHERE tr.embed_stale AND t.embedding_config IS NOT NULL "
        "  AND (t.embedding_config->>'enabled')::bool = TRUE "
        "LIMIT $1",
        BATCH_SIZE,
    )
    if not rows:
        return 0
    ids = []
    texts = []
    hashes = []
    for r in rows:
        text = _build_embedding_text(r["data"], r["embedding_config"], r["columns"])
        ids.append(r["id"])
        texts.append(text)
        hashes.append(_text_hash(text))
    vecs = await embedding_service.embed_batch(texts)
    if not vecs:
        return 0
    await pool.executemany(
        "UPDATE table_rows SET embedding = $1, content_hash = $2, embed_stale = FALSE WHERE id = $3",
        [(v, h, rid) for rid, v, h in zip(ids, vecs, hashes)],
    )
    return len(ids)


async def _reconcile_history_events() -> int:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, content FROM history_events WHERE embed_stale LIMIT $1",
        BATCH_SIZE,
    )
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    texts = [r["content"] or "" for r in rows]
    hashes = [_text_hash(t) for t in texts]
    vecs = await embedding_service.embed_batch(texts)
    if not vecs:
        return 0
    await pool.executemany(
        "UPDATE history_events SET embedding = $1, content_hash = $2, embed_stale = FALSE WHERE id = $3",
        [(v, h, eid) for eid, v, h in zip(ids, vecs, hashes)],
    )
    return len(ids)


async def _reconcile() -> int:
    if not embedding_service.is_configured():
        return 0
    done = 0
    for fn in (_reconcile_pages, _reconcile_table_rows, _reconcile_history_events):
        done += await fn()
    if done:
        logger.info("embedding reconciler: refreshed %d row(s)", done)
    return done


@celery.task(name="backend.tasks.embeddings.reconcile")
def reconcile() -> int:
    return run_async(_reconcile())
