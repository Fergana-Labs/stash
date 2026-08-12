"""The change feed the daily Memory curator reads.

`changes_since` is the incremental delta since the curator's watermark: new
history events (excluding the curator's own run sessions), changed pages
(excluding the Memory subtree), new files, changed Drive-folder documents,
and the user's connected sources as pointers (the agent pulls source
specifics with `stash search`) — the curator never sees its own output.
`has_changes_since` is the cheap EXISTS the beat task uses to skip idle users
without waking a sprite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..database import get_pool
from . import files_tree_service, source_service

# Caps so a single delta stays bounded (a long-idle account's first delta, a
# high-volume account's busy day). Overflowing _MAX_EVENTS never loses events:
# the watermark only advances through what fit (see complete_through), so the
# remainder is re-presented on the next run.
_MAX_EVENTS = 500
_MAX_PAGES = 100
_MAX_FILES = 100
_MAX_SAVES = 100
_MAX_SOURCE_DOCS = 100
_SNIPPET = 280

# Corrections are a rolling window, not part of the delta. Two reasons they
# can't ride the history feed: the feed drains oldest-first, so a backlogged
# account spends weeks of runs on old tool traffic before reaching this
# month's words; and tool events outnumber user messages by ~50:1, so user
# messages lose nearly every cap they compete for. (Measured on a real
# account, 2026-08: 500 feed events held 295 tool events and 6 user messages.)
# A single night also can't show recurrence, which is the whole test for a
# skill — so this window deliberately overlaps run to run.
_CORRECTION_WINDOW_DAYS = 30
# Sampled per session, not newest-first overall: a skill earns its slot on how
# many DISTINCT sessions show the pattern, so the input has to maximize
# sessions rather than messages. Measured on a real account (2026-08): the
# newest 200 messages covered 33 sessions over 1.4 days, while 4-per-session
# across 120 sessions covered 8 days for 279 messages.
_MAX_CORRECTION_SESSIONS = 120
_MAX_PER_SESSION = 4
_CORRECTION_SNIPPET = 600


async def has_changes_since(owner_user_id: UUID, user_id: UUID, since: datetime | None) -> bool:
    """True if anything the curator cares about changed after `since`. A cheap
    gate — the beat task skips a curator run (and the sprite wake) when False."""
    if since is None:
        return True  # never curated → bootstrap.
    pool = get_pool()
    memory_ids = await files_tree_service.memory_subtree_folder_ids(owner_user_id)
    exists = await pool.fetchval(
        """
        SELECT
          EXISTS (SELECT 1 FROM history_events
                  WHERE owner_user_id = $1 AND created_at > $2
                    AND (session_id IS NULL OR session_id NOT LIKE 'agent-curate-%'))
          OR EXISTS (SELECT 1 FROM pages
                     WHERE owner_user_id = $1 AND updated_at > $2
                       AND ($3::uuid[] IS NULL OR folder_id IS NULL
                            OR folder_id <> ALL($3)))
          OR EXISTS (SELECT 1 FROM files
                     WHERE owner_user_id = $1 AND created_at > $2)
          OR EXISTS (SELECT 1 FROM drive_documents
                     WHERE owner_user_id = $1 AND updated_at > $2
                       AND extraction_status = 'done' AND deleted_at IS NULL)
          OR EXISTS (SELECT 1 FROM x_save_docs
                     WHERE owner_user_id = $1 AND updated_at > $2
                       AND hydration_status = 'done' AND deleted_at IS NULL)
          OR EXISTS (SELECT 1 FROM instagram_save_docs
                     WHERE owner_user_id = $1 AND updated_at > $2
                       AND hydration_status = 'done' AND deleted_at IS NULL)
        """,
        owner_user_id,
        since,
        list(memory_ids) or None,
        column=0,
    )
    return bool(exists)


async def changes_since(owner_user_id: UUID, user_id: UUID, since: datetime | None) -> dict:
    """The delta the curator reads: history events, changed pages (excl. Memory),
    new files, changed Drive-folder documents, newly hydrated X/Instagram
    saves, and connected-source pointers."""
    pool = get_pool()
    memory_ids = await files_tree_service.memory_subtree_folder_ids(owner_user_id)
    exclude = list(memory_ids) or None

    events, history_has_more = await _feed_events(owner_user_id, since, None, _MAX_EVENTS)
    history = [
        {
            "session_id": e.get("session_id"),
            "agent_name": e.get("agent_name"),
            "event_type": e.get("event_type"),
            "content": (e.get("content") or "")[:_SNIPPET],
            "created_at": _iso(e.get("created_at")),
            "folder": e.get("folder"),
        }
        for e in events
    ]

    page_rows = await pool.fetch(
        """
        SELECT id, name, folder_id, updated_at,
               left(coalesce(content_markdown, ''), $4) AS snippet
        FROM pages
        WHERE owner_user_id = $1
          AND ($5::uuid[] IS NULL OR folder_id IS NULL OR folder_id <> ALL($5))
          AND ($2::timestamptz IS NULL OR updated_at > $2)
        ORDER BY updated_at DESC LIMIT $3
        """,
        owner_user_id,
        since,
        _MAX_PAGES,
        _SNIPPET,
        exclude,
    )
    pages = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "folder_id": str(r["folder_id"]) if r["folder_id"] else None,
            "updated_at": _iso(r["updated_at"]),
            "snippet": r["snippet"],
        }
        for r in page_rows
    ]

    file_rows = await pool.fetch(
        """
        SELECT id, name, created_at, left(coalesce(extracted_text, ''), $4) AS snippet
        FROM files
        WHERE owner_user_id = $1 AND ($2::timestamptz IS NULL OR created_at > $2)
        ORDER BY created_at DESC LIMIT $3
        """,
        owner_user_id,
        since,
        _MAX_FILES,
        _SNIPPET,
    )
    files = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "created_at": _iso(r["created_at"]),
            "snippet": r["snippet"],
        }
        for r in file_rows
    ]

    # Changed Drive-folder documents, as items rather than source pointers — a
    # picked Drive folder is the user's curated document set (edited outside
    # Stash), so an edit there is curation input the same way an upload is.
    # `updated_at` moves only on a real change: the sync upsert bumps it when
    # Drive's modifiedTime differs, and extraction bumps it when the new body
    # lands. Gating on 'done' presents a doc only once its text is readable.
    source_doc_rows = await pool.fetch(
        """
        SELECT path, name, updated_at, left(coalesce(content, ''), $4) AS snippet
        FROM drive_documents
        WHERE owner_user_id = $1
          AND ($2::timestamptz IS NULL OR updated_at > $2)
          AND extraction_status = 'done' AND deleted_at IS NULL
        ORDER BY updated_at DESC LIMIT $3
        """,
        owner_user_id,
        since,
        _MAX_SOURCE_DOCS,
        _SNIPPET,
    )
    source_docs = [
        {
            "path": r["path"],
            "name": r["name"],
            "updated_at": _iso(r["updated_at"]),
            "snippet": r["snippet"],
        }
        for r in source_doc_rows
    ]

    # Newly hydrated X/Instagram saves, as items rather than source pointers —
    # a save the user made is deliberate curation input, like an upload.
    save_rows = await pool.fetch(
        """
        SELECT source, kind, name, url, updated_at, snippet FROM (
            SELECT 'x' AS source, kind, name,
                   'https://x.com/i/status/' || external_ref AS url,
                   updated_at, left(coalesce(content, ''), $4) AS snippet
            FROM x_save_docs
            WHERE owner_user_id = $1
              AND ($2::timestamptz IS NULL OR updated_at > $2)
              AND hydration_status = 'done' AND deleted_at IS NULL
            UNION ALL
            SELECT 'instagram', kind, name,
                   'https://www.instagram.com/p/' || external_ref || '/',
                   updated_at, left(coalesce(content, ''), $4)
            FROM instagram_save_docs
            WHERE owner_user_id = $1
              AND ($2::timestamptz IS NULL OR updated_at > $2)
              AND hydration_status = 'done' AND deleted_at IS NULL
        ) all_saves
        ORDER BY updated_at DESC LIMIT $3
        """,
        owner_user_id,
        since,
        _MAX_SAVES,
        _SNIPPET,
    )
    saves = [
        {
            "source": r["source"],
            "kind": r["kind"],
            "name": r["name"],
            "url": r["url"],
            "updated_at": _iso(r["updated_at"]),
            "snippet": r["snippet"],
        }
        for r in save_rows
    ]

    all_sources = await source_service.list_sources(owner_user_id, user_id)
    sources = [
        {"source": s.get("source"), "type": s.get("type"), "display_name": s.get("display_name")}
        for s in all_sources
        if not str(s.get("type", "")).startswith("native_")
    ]

    corrections = await recent_user_messages(owner_user_id, datetime.now(UTC))

    return {
        "since": _iso(since),
        "correction_window_days": _CORRECTION_WINDOW_DAYS,
        "counts": {
            "history": len(history),
            "pages": len(pages),
            "files": len(files),
            "source_docs": len(source_docs),
            "saves": len(saves),
            "sources": len(sources),
            "corrections": len(corrections),
        },
        "history": history,
        "history_has_more": history_has_more,
        "corrections": corrections,
        "pages": pages,
        "files": files,
        "source_docs": source_docs,
        "saves": saves,
        "sources": sources,
    }


async def _feed_events(
    owner_user_id: UUID,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> tuple[list[dict], bool]:
    """The curator's event feed, oldest first. Returns (events, has_more).

    The curator's own run transcripts (`agent-curate-%` sessions) are excluded
    in SQL — feeding them back would echo-loop the daily gate and pollute the
    wiki, and filtering after the query would let them consume feed slots that
    belong to real activity.

    Each event carries its session's folder name: folder placement is the
    owner's curation signal (e.g. one folder per customer org, or a designated
    folder of expert-sanctioned traces), so the curator must see it."""
    pool = get_pool()
    args: list = [owner_user_id]
    where = "he.owner_user_id = $1 AND (he.session_id IS NULL OR he.session_id NOT LIKE 'agent-curate-%')"
    if since is not None:
        args.append(since)
        where += f" AND he.created_at > ${len(args)}"
    if until is not None:
        args.append(until)
        where += f" AND he.created_at <= ${len(args)}"
    rows = await pool.fetch(
        f"SELECT he.session_id, he.agent_name, he.event_type, he.content, he.created_at, "
        f"sf.name AS folder "
        f"FROM history_events he "
        f"LEFT JOIN sessions s ON s.owner_user_id = he.owner_user_id "
        f"  AND s.session_id = he.session_id "
        f"LEFT JOIN session_folders sf ON sf.id = s.session_folder_id "
        f"WHERE {where} "
        f"ORDER BY he.created_at, he.id LIMIT {limit + 1}",
        *args,
    )
    has_more = len(rows) > limit
    return [dict(r) for r in rows[:limit]], has_more


async def recent_user_messages(owner_user_id: UUID, now: datetime) -> list[dict]:
    """The user's own words from the last `_CORRECTION_WINDOW_DAYS` — the
    curator's evidence for what a skill should say. Up to `_MAX_PER_SESSION`
    messages from each of the `_MAX_CORRECTION_SESSIONS` most recent sessions,
    newest session first.

    Deliberately outside the watermark: this is a window, not a delta, so it
    never advances `complete_through` and re-presents the same messages night
    after night. That repetition is the point — a skill earns its slot on
    recurrence across sessions, which one night's delta cannot show."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        WITH ranked AS (
          SELECT he.session_id, he.agent_name, he.created_at,
                 left(coalesce(he.content, ''), $4) AS content,
                 row_number() OVER (PARTITION BY he.session_id
                                    ORDER BY he.created_at DESC) AS rn,
                 max(he.created_at) OVER (PARTITION BY he.session_id) AS session_last
          FROM history_events he
          WHERE he.owner_user_id = $1
            AND he.event_type = 'user_message'
            AND (he.session_id IS NULL OR he.session_id NOT LIKE 'agent-curate-%')
            AND he.created_at > $2
            AND coalesce(he.content, '') <> ''
        ),
        top_sessions AS (
          SELECT DISTINCT session_id, session_last FROM ranked
          ORDER BY session_last DESC LIMIT $3
        )
        SELECT r.session_id, r.agent_name, r.created_at, r.content, sf.name AS folder
        FROM ranked r
        JOIN top_sessions t ON t.session_id IS NOT DISTINCT FROM r.session_id
        LEFT JOIN sessions s ON s.owner_user_id = $1 AND s.session_id = r.session_id
        LEFT JOIN session_folders sf ON sf.id = s.session_folder_id
        WHERE r.rn <= $5
        ORDER BY t.session_last DESC, r.created_at
        """,
        owner_user_id,
        now - timedelta(days=_CORRECTION_WINDOW_DAYS),
        _MAX_CORRECTION_SESSIONS,
        _CORRECTION_SNIPPET,
        _MAX_PER_SESSION,
    )
    return [
        {
            "session_id": r["session_id"],
            "agent_name": r["agent_name"],
            "folder": r["folder"],
            "created_at": _iso(r["created_at"]),
            "content": r["content"],
        }
        for r in rows
    ]


async def complete_through(
    owner_user_id: UUID, since: datetime | None, until: datetime
) -> datetime:
    """How far the curator's watermark may advance after a successful run.

    The feed is complete through `until` unless it overflowed _MAX_EVENTS, in
    which case it is only complete through the last event that fit — minus a
    microsecond, so events sharing that exact timestamp are re-presented next
    run rather than skipped. Overflow therefore drains run by run and no event
    is ever silently dropped from curation."""
    events, has_more = await _feed_events(owner_user_id, since, until, _MAX_EVENTS)
    if not has_more:
        return until
    return events[-1]["created_at"] - timedelta(microseconds=1)


def _iso(dt) -> str | None:
    return dt.isoformat() if isinstance(dt, datetime) else None
