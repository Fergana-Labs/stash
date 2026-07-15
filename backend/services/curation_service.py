"""The change feed the daily Memory curator reads.

`changes_since` is the incremental delta since the curator's watermark: new
session activity as one digest line per session (the curator dispatches a
reader subagent per session; transcripts never ride the feed, and the
curator's own run sessions are excluded), changed pages (excluding the Memory
subtree), new files, and the user's connected sources as pointers (the agent
pulls source specifics with `stash search`) — the curator never sees its own
output. `has_changes_since` is the cheap EXISTS the beat task uses to skip
idle users without waking a sprite.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from ..database import get_pool
from . import files_tree_service, source_service

# Caps so a single delta stays bounded (a long-idle account's first delta, a
# high-volume account's busy day). The session cap is the inventory guard: a
# digest is ~200 chars regardless of the session's size, so root context
# scales with sessions/day, not events/day. Overflowing never loses anything:
# the watermark only advances through what fit (see complete_through), so the
# remainder is re-presented on the next run.
_MAX_SESSIONS = 500
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
                    AND session_id NOT LIKE 'agent-curate-%')
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
    """The delta the curator reads: session digests, changed pages (excl.
    Memory), new files, and connected-source pointers."""
    pool = get_pool()
    memory_ids = await files_tree_service.memory_subtree_folder_ids(owner_user_id)
    exclude = list(memory_ids) or None

    digests, sessions_has_more = await _feed_session_digests(
        owner_user_id, since, None, _MAX_SESSIONS
    )
    session_digests = [
        {
            "session_id": d["session_id"],
            "agent_name": d["agent_name"],
            "folder": d["folder"],
            "event_count": d["event_count"],
            "first_at": _iso(d["first_at"]),
            "last_at": _iso(d["last_at"]),
            "opening": d["opening"],
        }
        for d in digests
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
            "sessions": len(session_digests),
            "pages": len(pages),
            "files": len(files),
            "sources": len(sources),
        },
        "session_digests": session_digests,
        "sessions_has_more": sessions_has_more,
        "pages": pages,
        "files": files,
        "sources": sources,
    }


def _window(args: list, since: datetime | None, until: datetime | None) -> str:
    clause = ""
    if since is not None:
        args.append(since)
        clause += f" AND he.created_at > ${len(args)}"
    if until is not None:
        args.append(until)
        clause += f" AND he.created_at <= ${len(args)}"
    return clause


async def _feed_session_digests(
    owner_user_id: UUID,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> tuple[list[dict], bool]:
    """The curator's session inventory: one row per session with events in the
    window, ordered by each session's last event. Returns (digests, has_more).

    The order matters for the watermark: complete_through advances through the
    last session that fit, so an excluded session's last event is always after
    the watermark and the whole session re-presents next run.

    The curator's own run transcripts (`agent-curate-%` sessions) are excluded
    in SQL — feeding them back would echo-loop the daily gate and pollute the
    wiki, and filtering after the query would let them consume feed slots that
    belong to real activity.

    Each digest carries its session's folder name: folder placement is the
    owner's curation signal (e.g. one folder per customer org, or a designated
    folder of expert-sanctioned traces), so the curator must see it."""
    pool = get_pool()
    args: list = [owner_user_id]
    where = "he.owner_user_id = $1 AND he.session_id NOT LIKE 'agent-curate-%'" + _window(
        args, since, until
    )
    rows = await pool.fetch(
        f"SELECT he.session_id, count(*) AS event_count, "
        f"min(he.created_at) AS first_at, max(he.created_at) AS last_at, "
        f"max(he.agent_name) AS agent_name, max(sf.name) AS folder "
        f"FROM history_events he "
        f"LEFT JOIN sessions s ON s.owner_user_id = he.owner_user_id "
        f"  AND s.session_id = he.session_id "
        f"LEFT JOIN session_folders sf ON sf.id = s.session_folder_id "
        f"WHERE {where} "
        f"GROUP BY he.session_id "
        f"ORDER BY max(he.created_at), he.session_id LIMIT {limit + 1}",
        *args,
    )
    has_more = len(rows) > limit
    digests = [dict(r) for r in rows[:limit]]
    openings = await _session_openings(
        owner_user_id, [d["session_id"] for d in digests], since, until
    )
    for d in digests:
        d["opening"] = openings.get(d["session_id"])
    return digests, has_more


async def _session_openings(
    owner_user_id: UUID,
    session_ids: list[str],
    since: datetime | None,
    until: datetime | None,
) -> dict[str, str]:
    """Each session's first user message in the window, truncated — the one
    content peek a digest carries, so triage can judge substance cheaply."""
    if not session_ids:
        return {}
    pool = get_pool()
    args: list = [owner_user_id, session_ids]
    where = (
        "he.owner_user_id = $1 AND he.session_id = ANY($2) AND he.event_type = 'user_message'"
    ) + _window(args, since, until)
    rows = await pool.fetch(
        f"SELECT DISTINCT ON (he.session_id) he.session_id, "
        f"left(coalesce(he.content, ''), {_SNIPPET}) AS opening "
        f"FROM history_events he WHERE {where} "
        f"ORDER BY he.session_id, he.created_at, he.id",
        *args,
    )
    return {r["session_id"]: r["opening"] for r in rows}


async def complete_through(
    owner_user_id: UUID, since: datetime | None, until: datetime
) -> datetime:
    """How far the curator's watermark may advance after a successful run.

    The feed is complete through `until` unless the inventory overflowed
    _MAX_SESSIONS, in which case it is only complete through the last session
    that fit — its last event's timestamp, minus a microsecond, so sessions
    sharing that exact timestamp are re-presented next run rather than
    skipped. Overflow therefore drains run by run and no session is ever
    silently dropped from curation."""
    digests, has_more = await _feed_session_digests(owner_user_id, since, until, _MAX_SESSIONS)
    if not has_more:
        return until
    return digests[-1]["last_at"] - timedelta(microseconds=1)


def _iso(dt) -> str | None:
    return dt.isoformat() if isinstance(dt, datetime) else None
