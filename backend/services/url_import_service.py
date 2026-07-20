"""url_imports job rows: create, claim, resolve.

Mirrors the files.extraction_status lifecycle: rows are claimed with an
attempts guard so the Beat sweep and creation-time dispatch can both fire
without double work, and failures are recorded loudly per row.
"""

from uuid import UUID

from ..database import get_pool

MAX_ATTEMPTS = 3


async def create_url_imports(
    *,
    owner_user_id: UUID,
    created_by: UUID,
    items: list[dict],
    batch_id: UUID | None = None,
) -> list[UUID]:
    """Bulk-insert import rows. Each item: {url, title?, folder_id?}."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        INSERT INTO url_imports (owner_user_id, created_by, batch_id, url, title, folder_id)
        SELECT $1, $2, $3, i.url, i.title, i.folder_id
        FROM unnest($4::text[], $5::text[], $6::uuid[]) AS i(url, title, folder_id)
        RETURNING id
        """,
        owner_user_id,
        created_by,
        batch_id,
        [i["url"] for i in items],
        [i.get("title") for i in items],
        [i.get("folder_id") for i in items],
    )
    return [r["id"] for r in rows]


async def create_batch(
    *,
    owner_user_id: UUID,
    kind: str,
    filename: str | None,
    total: int,
) -> UUID:
    return await get_pool().fetchval(
        "INSERT INTO import_batches (owner_user_id, kind, filename, total) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        owner_user_id,
        kind,
        filename,
        total,
    )


async def get_url_import(import_id: UUID, owner_user_id: UUID) -> dict | None:
    row = await get_pool().fetchrow(
        "SELECT * FROM url_imports WHERE id = $1 AND owner_user_id = $2",
        import_id,
        owner_user_id,
    )
    return dict(row) if row else None


async def claim(import_id: UUID) -> dict | None:
    """Move a row to processing if it's still pending/retryable."""
    row = await get_pool().fetchrow(
        f"""
        UPDATE url_imports
        SET status = 'processing', locked_at = now(), attempts = attempts + 1,
            updated_at = now()
        WHERE id = $1
          AND (
                status = 'pending'
             OR (status = 'failed' AND attempts < {MAX_ATTEMPTS})
             OR (status = 'processing' AND locked_at < now() - INTERVAL '10 minutes')
          )
          AND (retry_at IS NULL OR retry_at < now())
        RETURNING *
        """,
        import_id,
    )
    return dict(row) if row else None


async def mark_done(
    import_id: UUID,
    *,
    page_id: UUID | None = None,
    file_id: UUID | None = None,
    error: str | None = None,
) -> None:
    """Resolve a row. A done row WITH an error is a link-only save: the
    bookmark row exists but content hydration gave up (the error says why)."""
    await get_pool().execute(
        "UPDATE url_imports SET status = 'done', error = $4, locked_at = NULL, "
        "result_page_id = $2, result_file_id = $3, updated_at = now() WHERE id = $1",
        import_id,
        page_id,
        file_id,
        error[:2000] if error else None,
    )


async def mark_failed(import_id: UUID, error: str) -> None:
    await get_pool().execute(
        "UPDATE url_imports SET status = 'failed', error = $2, locked_at = NULL, "
        "updated_at = now() WHERE id = $1",
        import_id,
        error[:2000],
    )


async def mark_rate_limited(import_id: UUID, *, retry_minutes: int = 15) -> None:
    """A 429 is the site pushing back, not a content failure: give the
    attempt back and park the row until the retry window passes."""
    await get_pool().execute(
        f"""
        UPDATE url_imports
        SET status = 'pending', attempts = greatest(attempts - 1, 0),
            retry_at = now() + INTERVAL '{retry_minutes} minutes',
            dispatched_at = NULL, locked_at = NULL, updated_at = now()
        WHERE id = $1
        """,
        import_id,
    )


async def mark_needs_client(import_id: UUID, error: str) -> None:
    """The server can't fetch this URL (login wall, IP block); hand it to
    the browser extension, which retries with the user's own session."""
    await get_pool().execute(
        "UPDATE url_imports SET status = 'needs_client', error = $2, locked_at = NULL, "
        "updated_at = now() WHERE id = $1",
        import_id,
        error[:2000],
    )


async def claim_client_batch(owner_user_id: UUID, *, limit: int) -> list[dict]:
    """Atomically claim needs_client rows for the extension to fetch.
    locked_at is the claim marker; stale claims (extension died mid-fetch)
    are reclaimable after 10 minutes."""
    rows = await get_pool().fetch(
        """
        UPDATE url_imports
        SET locked_at = now(), updated_at = now()
        WHERE id IN (
            SELECT id FROM url_imports
            WHERE owner_user_id = $1 AND status = 'needs_client'
              AND (locked_at IS NULL OR locked_at < now() - INTERVAL '10 minutes')
            ORDER BY created_at
            LIMIT $2
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, url
        """,
        owner_user_id,
        limit,
    )
    return [dict(r) for r in rows]


async def batch_progress(batch_id: UUID, owner_user_id: UUID) -> dict | None:
    pool = get_pool()
    batch = await pool.fetchrow(
        "SELECT id, kind, filename, total, created_at FROM import_batches "
        "WHERE id = $1 AND owner_user_id = $2",
        batch_id,
        owner_user_id,
    )
    if batch is None:
        return None
    counts = await pool.fetchrow(
        """
        SELECT
            count(*) FILTER (WHERE status = 'done' AND error IS NULL) AS done,
            count(*) FILTER (WHERE status = 'done' AND error IS NOT NULL) AS link_only,
            count(*) FILTER (WHERE status = 'needs_client') AS needs_client,
            count(*) FILTER (
                WHERE status IN ('pending', 'processing')
                   OR (status = 'failed' AND attempts < 3)
            ) AS pending
        FROM url_imports WHERE batch_id = $1
        """,
        batch_id,
    )
    link_only_rows = await pool.fetch(
        "SELECT url, error FROM url_imports "
        "WHERE batch_id = $1 AND status = 'done' AND error IS NOT NULL "
        "ORDER BY updated_at DESC LIMIT 50",
        batch_id,
    )
    return {
        **dict(batch),
        "done": counts["done"],
        "link_only": counts["link_only"],
        "needs_client": counts["needs_client"],
        "pending": counts["pending"],
        "failures": [dict(f) for f in link_only_rows],
    }
