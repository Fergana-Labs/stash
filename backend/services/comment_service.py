"""Page comment threads + messages.

A thread anchors to a span in the page content. The anchor lives both in
the content itself (the editor wraps the range in a
`<span data-comment-id="...">` on the client) and as `quoted_text` +
`prefix` / `suffix` here, so a thread whose inline anchor gets clobbered
can still be surfaced in the orphaned group with its original text.
"""

from uuid import UUID

from ..database import get_pool


def _thread_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "page_id": row["page_id"],
        "quoted_text": row["quoted_text"],
        "prefix": row["prefix"],
        "suffix": row["suffix"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
        "resolved_by": row["resolved_by"],
        "orphaned": row["orphaned"],
        "messages": [],
    }


def _message_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "author_id": row["author_id"],
        "author_name": row["author_name"] or "",
        "body": row["body"],
        "created_at": row["created_at"],
    }


async def list_threads(page_id: UUID) -> list[dict]:
    pool = get_pool()
    thread_rows = await pool.fetch(
        """
        SELECT id, page_id, quoted_text, prefix, suffix, created_by, created_at,
               resolved_at, resolved_by, orphaned
        FROM page_comment_threads
        WHERE page_id = $1
        ORDER BY created_at ASC
        """,
        page_id,
    )
    if not thread_rows:
        return []
    thread_ids = [r["id"] for r in thread_rows]
    message_rows = await pool.fetch(
        """
        SELECT m.id, m.thread_id, m.author_id, m.body, m.created_at,
               COALESCE(u.display_name, u.name) AS author_name
        FROM page_comment_messages m
        JOIN users u ON u.id = m.author_id
        WHERE m.thread_id = ANY($1::uuid[])
        ORDER BY m.created_at ASC
        """,
        thread_ids,
    )
    threads = [_thread_row_to_dict(r) for r in thread_rows]
    by_id = {t["id"]: t for t in threads}
    for mr in message_rows:
        thread = by_id.get(mr["thread_id"])
        if thread is None:
            continue
        thread["messages"].append(_message_row_to_dict(mr))
    return threads


async def _fetch_thread(thread_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, page_id, quoted_text, prefix, suffix, created_by, created_at,
               resolved_at, resolved_by, orphaned
        FROM page_comment_threads
        WHERE id = $1
        """,
        thread_id,
    )
    if row is None:
        return None
    thread = _thread_row_to_dict(row)
    message_rows = await pool.fetch(
        """
        SELECT m.id, m.thread_id, m.author_id, m.body, m.created_at,
               COALESCE(u.display_name, u.name) AS author_name
        FROM page_comment_messages m
        JOIN users u ON u.id = m.author_id
        WHERE m.thread_id = $1
        ORDER BY m.created_at ASC
        """,
        thread_id,
    )
    thread["messages"] = [_message_row_to_dict(mr) for mr in message_rows]
    return thread


async def create_thread(
    page_id: UUID,
    *,
    quoted_text: str,
    prefix: str,
    suffix: str,
    body: str,
    created_by: UUID,
) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            thread_id = await conn.fetchval(
                """
                INSERT INTO page_comment_threads
                  (page_id, quoted_text, prefix, suffix, created_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                page_id,
                quoted_text,
                prefix,
                suffix,
                created_by,
            )
            await conn.execute(
                """
                INSERT INTO page_comment_messages (thread_id, author_id, body)
                VALUES ($1, $2, $3)
                """,
                thread_id,
                created_by,
                body,
            )
    return await _fetch_thread(thread_id)


async def add_reply(thread_id: UUID, *, body: str, author_id: UUID) -> dict | None:
    pool = get_pool()
    exists = await pool.fetchval("SELECT 1 FROM page_comment_threads WHERE id = $1", thread_id)
    if not exists:
        return None
    await pool.execute(
        """
        INSERT INTO page_comment_messages (thread_id, author_id, body)
        VALUES ($1, $2, $3)
        """,
        thread_id,
        author_id,
        body,
    )
    return await _fetch_thread(thread_id)


async def set_resolved(thread_id: UUID, *, resolved: bool, user_id: UUID) -> dict | None:
    pool = get_pool()
    if resolved:
        updated = await pool.fetchval(
            """
            UPDATE page_comment_threads
            SET resolved_at = now(), resolved_by = $2
            WHERE id = $1
            RETURNING id
            """,
            thread_id,
            user_id,
        )
    else:
        updated = await pool.fetchval(
            """
            UPDATE page_comment_threads
            SET resolved_at = NULL, resolved_by = NULL
            WHERE id = $1
            RETURNING id
            """,
            thread_id,
        )
    if updated is None:
        return None
    return await _fetch_thread(thread_id)


async def delete_message(message_id: UUID, *, user_id: UUID) -> tuple[str, dict | None]:
    """Delete a single message. The author is the only one allowed.

    Returns (status, thread):
      ("not_found", None) — no such message
      ("forbidden", None) — caller is not the author
      ("ok", thread)      — message removed, returns the updated thread
      ("ok_thread_gone", None) — last message removed, thread auto-deleted
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT thread_id, author_id FROM page_comment_messages WHERE id = $1",
        message_id,
    )
    if row is None:
        return ("not_found", None)
    if row["author_id"] != user_id:
        return ("forbidden", None)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM page_comment_messages WHERE id = $1", message_id)
            remaining = await conn.fetchval(
                "SELECT COUNT(*) FROM page_comment_messages WHERE thread_id = $1",
                row["thread_id"],
            )
            if remaining == 0:
                await conn.execute(
                    "DELETE FROM page_comment_threads WHERE id = $1",
                    row["thread_id"],
                )
                return ("ok_thread_gone", None)
    return ("ok", await _fetch_thread(row["thread_id"]))


async def delete_thread(thread_id: UUID, *, user_id: UUID) -> str:
    """Delete an entire thread and its messages. Only the thread creator
    is allowed. The frontend should also strip the inline anchor span from
    the page content so the highlight clears.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT created_by FROM page_comment_threads WHERE id = $1",
        thread_id,
    )
    if row is None:
        return "not_found"
    if row["created_by"] != user_id:
        return "forbidden"
    await pool.execute("DELETE FROM page_comment_threads WHERE id = $1", thread_id)
    return "ok"


async def reconcile_orphans(page_id: UUID, present_ids: list[UUID]) -> None:
    """Mark threads not in present_ids as orphaned; un-orphan ones that are.

    Called by the editor after every save with the set of `data-comment-id`s
    still present in the saved content.
    """
    pool = get_pool()
    if present_ids:
        await pool.execute(
            """
            UPDATE page_comment_threads
            SET orphaned = (id <> ALL($2::uuid[]))
            WHERE page_id = $1
              AND resolved_at IS NULL
              AND orphaned <> (id <> ALL($2::uuid[]))
            """,
            page_id,
            present_ids,
        )
    else:
        await pool.execute(
            """
            UPDATE page_comment_threads
            SET orphaned = TRUE
            WHERE page_id = $1 AND resolved_at IS NULL AND orphaned = FALSE
            """,
            page_id,
        )
