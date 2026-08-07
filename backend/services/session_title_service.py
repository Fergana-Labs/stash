"""AI-generated and fallback readable titles for sessions."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from uuid import UUID

from ..config import settings
from ..database import get_pool

MAX_TITLE_LENGTH = 80
ENQUEUE_MISSING_LIMIT = 40

_USER_EVENT_TYPES = (
    "user_message",
    "user_prompt",
    "prompt",
    "message",
    "user",
)
_ASSISTANT_EVENT_TYPES = ("assistant_message", "assistant")

# Generated output that converses with the transcript instead of naming the
# task — a reply ("You're right—…") or a refusal ("I need more context…").
# The 2026-05 backfill cached hundreds of these as titles; reject them so a
# conversational LLM response is never stored again.
_REPLY_SHAPED = re.compile(
    r"^(you're |you are |i'll |i've |i'd |i'm |i am |i need |i don't |i do not |"
    r"i cannot |i can't |i apologize|i appreciate |unable to |yes[,—. ]|no[,—. ]|"
    r"sure[,. ]|okay[,. ]|thanks|great question|your |"
    r"(perfect|pong|done|great)[.!]?$)",
    re.IGNORECASE,
)


def source_hash(session: dict) -> str:
    last_at = session.get("last_at") or session.get("last_event_at") or session.get("updated_at")
    if isinstance(last_at, datetime):
        last_at = last_at.isoformat()
    raw = f"{session['session_id']}|{session.get('event_count')}|{last_at or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def titles_for_sessions(
    owner_user_id: UUID,
    sessions: list[dict],
    *,
    enqueue_missing: bool = True,
) -> dict[str, str]:
    if not sessions:
        return {}

    pool = get_pool()
    session_ids = [s["session_id"] for s in sessions]
    rows = await pool.fetch(
        "SELECT session_id, title, title_source_hash AS source_hash, "
        "       title_user_set AS user_set "
        "FROM sessions "
        "WHERE owner_user_id = $1 AND session_id = ANY($2::text[]) AND title IS NOT NULL",
        owner_user_id,
        session_ids,
    )
    cached = {r["session_id"]: dict(r) for r in rows}

    titles: dict[str, str] = {}
    stale_session_ids: list[str] = []
    for session in sessions:
        session_id = session["session_id"]
        title_row = cached.get(session_id)
        session_source_hash = source_hash(session)
        if title_row:
            titles[session_id] = title_row["title"]
        else:
            titles[session_id] = title_from_text(session.get("title_source"), session_id)

        if title_row and title_row.get("user_set"):
            continue
        if title_row and title_row["source_hash"] == session_source_hash:
            continue
        stale_session_ids.append(session_id)

    if enqueue_missing and stale_session_ids:
        _enqueue_title_generation(owner_user_id, stale_session_ids[:ENQUEUE_MISSING_LIMIT])

    return titles


async def title_for_events(owner_user_id: UUID, session_id: str, events: list[dict]) -> str:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT title FROM sessions "
        "WHERE owner_user_id = $1 AND session_id = $2 AND title IS NOT NULL",
        owner_user_id,
        session_id,
    )
    if row:
        return row["title"]

    _enqueue_title_generation(owner_user_id, [session_id])
    return title_from_events(events, session_id)


async def set_user_title(owner_user_id: UUID, session_id: str, title: str) -> str:
    """Persist a user-provided title. Future auto-generation skips this row.

    Returns the cleaned title that was stored.
    """
    cleaned = _truncate(_strip_quotes(title).strip())
    if not cleaned:
        raise ValueError("Title cannot be empty")
    pool = get_pool()
    status = await pool.execute(
        """
        UPDATE sessions SET
          title = $3,
          title_source_hash = '',
          title_user_set = TRUE,
          title_updated_at = now()
        WHERE owner_user_id = $1 AND session_id = $2
        """,
        owner_user_id,
        session_id,
        cleaned,
    )
    if status == "UPDATE 0":
        raise ValueError("Session not found")
    return cleaned


def _enqueue_title_generation(owner_user_id: UUID, session_ids: list[str]) -> None:
    if not settings.ANTHROPIC_API_KEY:
        return

    from ..tasks.session_titles import generate_session_title

    for session_id in session_ids:
        generate_session_title.delay(str(owner_user_id), session_id)


async def titles_for_session_ids(owner_user_id: UUID, session_ids: list[str]) -> dict[str, str]:
    """Display titles for a bounded set of session ids — cached titles where
    they exist, otherwise the same first-event fallback the overview computes,
    so callers (e.g. search results) name sessions exactly as the sidebar and
    VFS do. Never enqueues title generation."""
    if not session_ids:
        return {}
    rows = await get_pool().fetch(
        "SELECT DISTINCT ON (ht.session_id) "
        "  ht.session_id, LEFT(ht.content, 240) AS title_source "
        "FROM history_events ht "
        "WHERE ht.owner_user_id = $1 AND ht.session_id = ANY($2::text[]) "
        "  AND NULLIF(BTRIM(ht.content), '') IS NOT NULL "
        "ORDER BY ht.session_id, CASE "
        "  WHEN ht.event_type IN ('user_message', 'user_prompt', 'prompt', 'message', 'user') THEN 0 "
        "  WHEN ht.event_type IN ('assistant_message', 'assistant') THEN 1 "
        "  ELSE 2 "
        "END, ht.created_at, ht.id",
        owner_user_id,
        session_ids,
    )
    sources = {r["session_id"]: r["title_source"] for r in rows}
    sessions = [{"session_id": sid, "title_source": sources.get(sid)} for sid in session_ids]
    return await titles_for_sessions(owner_user_id, sessions, enqueue_missing=False)


def title_from_text(text: str | None, session_id: str) -> str:
    title = _title_from_content(text)
    if title:
        return _truncate(_strip_quotes(title))
    return session_id


def title_from_events(events: list[dict], session_id: str) -> str:
    for event_type in (_USER_EVENT_TYPES, _ASSISTANT_EVENT_TYPES):
        title = _title_from_first_matching_event(events, event_type)
        if title:
            return _truncate(_strip_quotes(title))
    return session_id


def clean_generated_title(text: str) -> str:
    title = re.sub(r"\s+", " ", text).strip("`\"' ")
    title = re.sub(r"^\s*title:\s*", "", title, flags=re.IGNORECASE)
    title = _strip_markdown(title)
    # Reply detection needs the apostrophes ("I'll …", "you're …") — strip
    # quotes only after the title passes it.
    if not title or _REPLY_SHAPED.match(title):
        return ""
    return _truncate(_strip_quotes(_first_clause(title)))


def _title_from_first_matching_event(events: list[dict], event_types: tuple[str, ...]) -> str:
    for event in events:
        if event.get("event_type") not in event_types:
            continue
        title = _title_from_content(event.get("content"))
        if title:
            return title
    return ""


def _title_from_content(content: str | None) -> str:
    title = _title_from_structured_context(content)
    if title:
        return title

    for line in (content or "").splitlines():
        title = _title_from_line(line)
        if title:
            return title
    return ""


def _title_from_structured_context(content: str | None) -> str:
    lines = (content or "").splitlines()
    first_line = next((line.strip() for line in lines if line.strip()), "")
    if not first_line.lower().startswith("you are working on a linear ticket"):
        return ""

    for line in lines:
        match = re.match(r"^\s*Title:\s*(.+?)\s*$", line)
        if not match:
            continue
        return _title_from_line(match.group(1))

    return ""


def _title_from_line(line: str) -> str:
    text = _strip_markdown(line)
    if not text:
        return ""

    text = _strip_lead_in(text)
    if not text:
        return ""

    return _first_clause(text)


def _strip_markdown(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return text.strip(" \t*_")


def _first_clause(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    match = re.match(r"(.+?)[.!?](?:\s|$)", one_line)
    if match:
        return match.group(1).strip()
    return one_line


def _strip_lead_in(text: str) -> str:
    lower = text.lower()
    for phrase in ("please ", "can you ", "could you "):
        if lower.startswith(phrase):
            return _capitalize_first(text[len(phrase) :].strip())
    return text


def _strip_quotes(text: str) -> str:
    # Titles become VFS directory names and search-hit names, and agents reach
    # those through `stash vfs "<script>"` — quotes and backticks in a title
    # don't survive that shell parsing, so no stored title may contain them.
    return re.sub(r"['\"`]", "", text)


def _truncate(title: str) -> str:
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    return title[:MAX_TITLE_LENGTH]


def _capitalize_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]
