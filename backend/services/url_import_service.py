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
) -> None:
    await get_pool().execute(
        "UPDATE url_imports SET status = 'done', error = NULL, locked_at = NULL, "
        "result_page_id = $2, result_file_id = $3, updated_at = now() WHERE id = $1",
        import_id,
        page_id,
        file_id,
    )


async def mark_failed(import_id: UUID, error: str) -> None:
    await get_pool().execute(
        "UPDATE url_imports SET status = 'failed', error = $2, locked_at = NULL, "
        "updated_at = now() WHERE id = $1",
        import_id,
        error[:2000],
    )


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
            count(*) FILTER (WHERE status = 'done') AS done,
            count(*) FILTER (WHERE status = 'failed' AND attempts >= 3) AS failed,
            count(*) FILTER (
                WHERE status IN ('pending', 'processing')
                   OR (status = 'failed' AND attempts < 3)
            ) AS pending
        FROM url_imports WHERE batch_id = $1
        """,
        batch_id,
    )
    failures = await pool.fetch(
        "SELECT url, error FROM url_imports "
        "WHERE batch_id = $1 AND status = 'failed' ORDER BY updated_at DESC LIMIT 50",
        batch_id,
    )
    return {
        **dict(batch),
        "done": counts["done"],
        "failed": counts["failed"],
        "pending": counts["pending"],
        "failures": [dict(f) for f in failures],
    }
