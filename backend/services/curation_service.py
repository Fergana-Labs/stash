"""The change feed the daily Memory curator reads.

`changes_since` is the incremental delta since the curator's watermark: new
history events (excluding the curator's own run sessions), changed pages
(excluding the Memory subtree), new files, and the user's connected sources as
pointers (the agent pulls source specifics with `stash search`) — the curator
never sees its own output. `has_changes_since` is the cheap EXISTS the beat
task uses to skip idle users without waking a sprite.
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
_SNIPPET = 280


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
        """,
        owner_user_id,
        since,
        list(memory_ids) or None,
        column=0,
    )
    return bool(exists)


async def changes_since(owner_user_id: UUID, user_id: UUID, since: datetime | None) -> dict:
    """The delta the curator reads: history events, changed pages (excl. Memory),
    new files, and connected-source pointers."""
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

    all_sources = await source_service.list_sources(owner_user_id, user_id)
    sources = [
        {"source": s.get("source"), "type": s.get("type"), "display_name": s.get("display_name")}
        for s in all_sources
        if not str(s.get("type", "")).startswith("native_")
    ]

    return {
        "since": _iso(since),
        "counts": {
            "history": len(history),
            "pages": len(pages),
            "files": len(files),
            "sources": len(sources),
        },
        "history": history,
        "history_has_more": history_has_more,
        "pages": pages,
        "files": files,
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
    belong to real activity."""
    pool = get_pool()
    args: list = [owner_user_id]
    where = "owner_user_id = $1 AND (session_id IS NULL OR session_id NOT LIKE 'agent-curate-%')"
    if since is not None:
        args.append(since)
        where += f" AND created_at > ${len(args)}"
    if until is not None:
        args.append(until)
        where += f" AND created_at <= ${len(args)}"
    rows = await pool.fetch(
        f"SELECT session_id, agent_name, event_type, content, created_at "
        f"FROM history_events WHERE {where} "
        f"ORDER BY created_at, id LIMIT {limit + 1}",
        *args,
    )
    has_more = len(rows) > limit
    return [dict(r) for r in rows[:limit]], has_more


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
