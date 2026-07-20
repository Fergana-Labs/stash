"""URL-import worker: fetch URL-only clips out-of-band.

Work arrives in batches of ids rather than one task per URL, and the
dispatcher only keeps WINDOW_URLS in flight at once — a 40k bookmark
import trickles through 2 of the worker's 4 slots instead of starving
embeddings and syncs behind a flooded queue. Batches are interleaved
across domains and fetches are capped per domain, because bookmark files
cluster heavily (a quarter of a real export is youtube.com) and hammering
one site from a datacenter IP is how imports get rate-limited.

Failure routing, in order of preference:
  - 429                → park the row (retry_at) without burning an attempt
  - 401/403 from the   → needs_client: the browser extension refetches with
    bookmark's own host   the user's session (import_fetch.ts)
  - no usable content  → link-only bookmark, immediately (retry can't help)
  - anything else      → retry up to MAX_ATTEMPTS, then link-only bookmark

Every row therefore ends as either a hydrated clip or a link-only bookmark
— an imported bookmark is never silently lost, and the row's error says
why content is missing.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from urllib.parse import urlparse
from uuid import UUID

import httpx

from ..celery_app import celery
from ..database import get_pool
from ..services import clip_router, clip_service, url_import_service
from ..services.article_extraction import ArticleExtractionError
from ..services.youtube_transcript import TranscriptUnavailable
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
CONCURRENCY = 8
PER_DOMAIN_CONCURRENCY = 2
# 2 batches in flight leaves 2 of the worker's 4 slots free for other work.
WINDOW_URLS = 2 * BATCH_SIZE
NEEDS_CLIENT_EXPIRY_HOURS = 24
EXPIRY_SWEEP_LIMIT = 200


async def _process_one(import_id: UUID) -> None:
    row = await url_import_service.claim(import_id)
    if row is None:
        return
    try:
        result = await clip_router.process_url_import(row)
    except (
        clip_router.UnsupportedUrlContent,
        ArticleExtractionError,
        TranscriptUnavailable,
    ) as exc:
        # Deterministic no-content outcomes: retrying can't produce content,
        # but the link itself is still worth keeping.
        await _resolve_link_only(row, f"{type(exc).__name__}: {exc}")
    except httpx.HTTPStatusError as exc:
        await _resolve_http_error(row, exc)
    except Exception as exc:
        logger.warning(
            "url import failed id=%s exception_type=%s",
            import_id,
            type(exc).__name__,
        )
        await _resolve_failure(row, f"{type(exc).__name__}: {exc}")
    else:
        await url_import_service.mark_done(
            row["id"],
            page_id=result.get("page_id"),
            file_id=result.get("file_id"),
        )


async def _resolve_http_error(row: dict, exc: httpx.HTTPStatusError) -> None:
    code = exc.response.status_code
    # 401/403 count as client-recoverable only when the bookmark's own site
    # sent them (login wall, IP block) — the same status from a third-party
    # API call (ScrapeCreators) means our config is broken, not the site.
    from_bookmark_host = exc.request.url.host == urlparse(row["url"]).hostname
    if code in (401, 403) and from_bookmark_host:
        await url_import_service.mark_needs_client(row["id"], f"HTTP {code}")
    elif code == 429 and row["attempts"] < url_import_service.MAX_ATTEMPTS:
        await url_import_service.mark_rate_limited(row["id"])
    elif code == 429 and from_bookmark_host:
        await url_import_service.mark_needs_client(row["id"], "HTTP 429 (rate limited)")
    else:
        await _resolve_failure(row, f"HTTP {code} from {exc.request.url.host}")


async def _resolve_failure(row: dict, error: str) -> None:
    if row["attempts"] >= url_import_service.MAX_ATTEMPTS:
        await _resolve_link_only(row, error)
    else:
        await url_import_service.mark_failed(row["id"], error)


async def _resolve_link_only(row: dict, error: str) -> None:
    await clip_service.save_link_only(
        row["owner_user_id"],
        row["created_by"],
        url=row["url"],
        title=row.get("title"),
    )
    await url_import_service.mark_done(row["id"], error=error)


async def _process_batch(ids: list[UUID]) -> str:
    rows = await get_pool().fetch("SELECT id, url FROM url_imports WHERE id = ANY($1)", ids)
    overall = asyncio.Semaphore(CONCURRENCY)
    per_domain: dict[str, asyncio.Semaphore] = defaultdict(
        lambda: asyncio.Semaphore(PER_DOMAIN_CONCURRENCY)
    )

    async def bounded(import_id: UUID, url: str) -> None:
        async with per_domain[urlparse(url).netloc], overall:
            await _process_one(import_id)

    await asyncio.gather(*(bounded(r["id"], r["url"]) for r in rows))
    return f"processed {len(rows)}"


@celery.task(name="backend.tasks.clips.process_url_imports")
def process_url_imports(ids: list[str]) -> str:
    return run_async(_process_batch([UUID(i) for i in ids]))


def _interleave_by_domain(rows: list[dict]) -> list[dict]:
    """Round-robin rows across domains so no batch hammers a single site."""
    queues: dict[str, deque] = defaultdict(deque)
    for row in rows:
        queues[urlparse(row["url"]).netloc].append(row)
    order = deque(queues.values())
    interleaved: list[dict] = []
    while order:
        queue = order.popleft()
        interleaved.append(queue.popleft())
        if queue:
            order.append(queue)
    return interleaved


async def dispatch_url_imports(ids: list[UUID]) -> None:
    """Interactive path (single async clip): dispatch immediately, bypassing
    the bulk window so one YouTube clip never queues behind a 40k import."""
    await get_pool().execute("UPDATE url_imports SET dispatched_at = now() WHERE id = ANY($1)", ids)
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start : start + BATCH_SIZE]
        process_url_imports.delay([str(i) for i in chunk])


async def top_up_url_imports() -> int:
    """Dispatch eligible rows up to the in-flight window. Called at import
    creation and by the Beat sweep; the dispatched_at bookkeeping makes the
    two safe to overlap, and re-dispatches rows whose task was lost (Redis
    blip, worker death) once their dispatched_at goes stale."""
    pool = get_pool()
    in_flight = await pool.fetchval(
        """
        SELECT count(*) FROM url_imports
        WHERE status = 'processing'
           OR (status = 'pending' AND dispatched_at > now() - INTERVAL '2 minutes')
        """
    )
    capacity = WINDOW_URLS - in_flight
    if capacity <= 0:
        return 0
    rows = await pool.fetch(
        f"""
        SELECT id, url FROM url_imports
        WHERE (
                (status = 'pending'
                 AND (dispatched_at IS NULL OR dispatched_at < now() - INTERVAL '2 minutes'))
             OR (status = 'failed' AND attempts < {url_import_service.MAX_ATTEMPTS})
             OR (status = 'processing' AND locked_at < now() - INTERVAL '10 minutes')
        )
          AND (retry_at IS NULL OR retry_at < now())
        ORDER BY created_at
        LIMIT $1
        """,
        capacity,
    )
    if not rows:
        return 0
    ordered = _interleave_by_domain([dict(r) for r in rows])
    ids = [r["id"] for r in ordered]
    await pool.execute("UPDATE url_imports SET dispatched_at = now() WHERE id = ANY($1)", ids)
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start : start + BATCH_SIZE]
        process_url_imports.delay([str(i) for i in chunk])
    return len(ids)


async def _expire_needs_client() -> int:
    """needs_client rows nobody's extension picked up resolve as link-only
    bookmarks — a batch must never hang open waiting for a client that
    doesn't exist."""
    rows = await get_pool().fetch(
        f"""
        SELECT * FROM url_imports
        WHERE status = 'needs_client'
          AND updated_at < now() - INTERVAL '{NEEDS_CLIENT_EXPIRY_HOURS} hours'
        ORDER BY created_at
        LIMIT {EXPIRY_SWEEP_LIMIT}
        """
    )
    for row in rows:
        record = dict(row)
        await _resolve_link_only(
            record,
            f"{record['error']}; no browser extension fetched it "
            f"within {NEEDS_CLIENT_EXPIRY_HOURS}h",
        )
    return len(rows)


async def _sweep() -> int:
    expired = await _expire_needs_client()
    if expired:
        logger.info("expired %d needs_client url imports to link-only", expired)
    return await top_up_url_imports()


@celery.task(name="backend.tasks.clips.enqueue_pending_url_imports")
def enqueue_pending_url_imports() -> int:
    return run_async(_sweep())
