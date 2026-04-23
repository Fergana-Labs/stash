"""Background reconciler for stale embeddings.

Fire-and-forget embeds can fail (provider 5xx, crash, etc.). When they
do, the service layer flips `embed_stale=true` on the row. This worker
periodically picks up those rows, re-embeds in batches through the
shared semaphore, and clears the flag.

One reconciler per uvicorn worker. Query uses the partial indexes
created in migration 0016, so the scan is cheap even at scale.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

from ..database import get_pool
from ..services import embeddings as embedding_service
from ..services.table_service import _build_embedding_text

logger = logging.getLogger(__name__)

BATCH_SIZE = 32
TICK_SECONDS = 30.0
ERROR_SLEEP_SECONDS = 30.0


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _reconcile_notebook_pages() -> int:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, content_markdown FROM notebook_pages " "WHERE embed_stale LIMIT $1",
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
        "UPDATE notebook_pages SET embedding = $1, embed_stale = FALSE WHERE id = $2",
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


async def _tick() -> int:
    if not embedding_service.is_configured():
        return 0
    done = 0
    for reconcile in (_reconcile_notebook_pages, _reconcile_table_rows, _reconcile_history_events):
        done += await reconcile()
    return done


async def run() -> None:
    """Run until cancelled. Safe to start from FastAPI lifespan."""
    logger.info("embedding reconciler started")
    while True:
        try:
            count = await _tick()
            if count:
                logger.info("embedding reconciler: refreshed %d row(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("embedding reconciler tick failed")
            await asyncio.sleep(ERROR_SLEEP_SECONDS)
            continue
        await asyncio.sleep(TICK_SECONDS)
