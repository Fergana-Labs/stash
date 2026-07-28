"""Broken-link checking for mini program tables.

Writes OK / Broken into the manifest's `status` column so "Broken" is just a
filter over the same list, the way Raindrop models it, rather than a separate
screen with its own storage.

Two things keep this from generating false alarms, which is the failure mode
that makes link checkers useless:

  - Only a 404/410 counts as broken. A 403, a 429, a timeout, or a TLS error
    means "we couldn't tell" — Cloudflare and consent walls return those to
    non-browser clients constantly, and marking those Broken trains people to
    ignore the filter.
  - HEAD first, GET on 405, and a browser User-Agent, because a lot of hosts
    reject either the method or the agent rather than the URL.

Re-checks are cheap but not free, so a URL is only re-checked once it hasn't
been looked at for RECHECK_DAYS.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit
from uuid import UUID

import httpx

from ..celery_app import celery
from ..database import get_pool
from ..services import mini_program_query, mini_program_service
from ._celery_helpers import run_async

logger = logging.getLogger(__name__)

BATCH_SIZE = 40
CONCURRENCY = 8
TIMEOUT = 12
RECHECK_DAYS = 30
MAX_REDIRECTS = 5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

STATUS_OK = "OK"
STATUS_BROKEN = mini_program_query.STATUS_BROKEN
# Only these mean the page is genuinely gone.
_DEAD_CODES = {404, 410}


async def _is_public_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    loop = asyncio.get_running_loop()
    try:
        addresses = await loop.getaddrinfo(
            parsed.hostname,
            port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(address[4][0]).is_global for address in addresses
    )


async def _probe(client: httpx.AsyncClient, url: str) -> str | None:
    """OK / Broken, or None when the result is inconclusive and the row should
    be left exactly as it is."""
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        if not await _is_public_url(current_url):
            return None
        try:
            response = await client.head(current_url)
            if response.status_code == 405:
                response = await client.get(current_url)
        except httpx.HTTPError:
            return None
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                return None
            current_url = urljoin(current_url, location)
            continue
        if response.status_code in _DEAD_CODES:
            return STATUS_BROKEN
        if response.status_code < 400:
            return STATUS_OK
        return None
    return None


async def _check_table(table_id: UUID, slots: dict, cutoff: datetime) -> int:
    link_col, status_col = slots.get("link"), slots.get("status")
    if not link_col or not status_col:
        return 0

    rows = await get_pool().fetch(
        "SELECT id, data FROM table_rows "
        "WHERE table_id = $1 AND (link_checked_at IS NULL OR link_checked_at < $2) "
        "ORDER BY link_checked_at NULLS FIRST LIMIT $3",
        table_id,
        cutoff,
        BATCH_SIZE,
    )
    if not rows:
        return 0

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _one(row) -> tuple[UUID, str | None]:
        url = str(row["data"].get(link_col) or "")
        if not url.startswith(("http://", "https://")):
            return row["id"], None
        async with semaphore:
            return row["id"], await _probe(client, url)

    async with httpx.AsyncClient(
        follow_redirects=False, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
    ) as client:
        results = await asyncio.gather(*(_one(row) for row in rows))

    now = datetime.now(UTC)
    checked = 0
    for row_id, verdict in results:
        # Stamp every row we looked at, so an inconclusive result doesn't make
        # the same URL the head of the queue forever.
        if verdict is None:
            await get_pool().execute(
                "UPDATE table_rows SET link_checked_at = $1 WHERE id = $2", now, row_id
            )
            continue
        await get_pool().execute(
            "UPDATE table_rows SET data = jsonb_set(data, ARRAY[$1], to_jsonb($2::text)), "
            "  link_checked_at = $3 WHERE id = $4",
            status_col,
            verdict,
            now,
            row_id,
        )
        checked += 1
    return checked


async def _reconcile() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=RECHECK_DAYS)
    tables = await get_pool().fetch(
        "SELECT id, mini_program, columns FROM tables WHERE mini_program IS NOT NULL"
    )
    total = 0
    for table in tables:
        manifest = mini_program_service.get_manifest(table["mini_program"])
        if manifest is None:
            continue
        slots = mini_program_service.resolve(manifest, table["columns"])["detail"]
        total += await _check_table(table["id"], slots, cutoff)
    return total


@celery.task(name="backend.tasks.link_check.reconcile")
def reconcile() -> int:
    return run_async(_reconcile())
