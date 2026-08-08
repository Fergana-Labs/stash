"""Granola → granola_notes indexer (scheduled pull, via the MCP server).

Opens an MCP session to Granola (bearer token, refreshed on demand) and pulls
meetings with `list_meetings`, then each meeting's transcript with
`get_meeting_transcript`. Each meeting's rendered markdown lands in granola_notes
(FTS + embeddings), filed under a month/day path ("2026-07/06 Standup (id8)") so
the notes list chronologically instead of by opaque meeting id. Idempotent
re-sync is handled upstream (content-hash dedupe + soft-delete of vanished
meetings).

Note: the exact JSON field names returned by Granola's MCP tools are only
visible from an authenticated `tools/list`, so the small parse helpers below
(`_meeting_id`, `_render_meeting`) encode the documented shape and are the one
spot to adjust against a live account.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from ...database import get_pool
from ...services import source_service
from .client import call_tool_data, granola_session
from .oauth import get_valid_access_token

logger = logging.getLogger(__name__)

# Granola rate-limits; a transcript fetch per meeting can add up, so cap a sync.
MAX_MEETINGS = 1000

# Granola's MCP tool names aren't a stable public contract, so we discover them
# at runtime (tools/list) and match by intent rather than hardcoding a guess.
_LIST_HINTS = (
    "list_meeting",
    "list_document",
    "list_note",
    "recent",
    "meeting",
    "document",
    "search",
)
_TRANSCRIPT_HINTS = ("transcript", "get_meeting", "get_document", "get_note", "detail", "content")


def _pick_tool(names: list[str], hints: tuple[str, ...]) -> str | None:
    lower = {n.lower(): n for n in names}
    for hint in hints:
        for low, original in lower.items():
            if hint in low:
                return original
    return None


def _meeting_id(meeting: dict) -> str | None:
    return meeting.get("id") or meeting.get("meeting_id") or meeting.get("document_id")


# Granola's list_meetings returns an XML-ish text blob (not JSON), wrapped in a
# <meetings_data ... count="N"> envelope:
#   <meetings_data ... count="2">
#     <meeting id=".." title=".." date=".." captured_by_me=".." ...>…</meeting>
#   </meetings_data>
# It isn't valid XML (participant emails contain raw <>), so parse with a regex.
# The <meeting> tag gains attributes over time, so match the whole tag and read
# attributes by name — anchoring to a fixed attribute order silently returned
# zero meetings once Granola added attributes after `date` (2026-08).
_MEETINGS_COUNT_RE = re.compile(r'<meetings_data\b[^>]*\bcount="(?P<count>\d+)"')
_MEETING_BLOCK_RE = re.compile(r"<meeting\s+(?P<attrs>[^>]*?)>(?P<body>.*?)</meeting>", re.DOTALL)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _declared_meeting_count(text: str) -> int | None:
    """Granola states its own meeting tally on the envelope. None if the
    envelope is absent, which itself means the response is not what we expect."""
    match = _MEETINGS_COUNT_RE.search(text)
    return int(match.group("count")) if match else None


def _parse_meetings_text(text: str) -> list[dict]:
    meetings = []
    for block in _MEETING_BLOCK_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(block.group("attrs")))
        if not attrs.get("id"):
            continue
        participants = re.sub(r"</?known_participants>", "", block.group("body"))
        participants = " ".join(participants.split())
        meetings.append(
            {
                "id": attrs["id"],
                "title": attrs.get("title") or "Untitled meeting",
                "date": attrs.get("date"),
                "participants": participants,
            }
        )
    return meetings


def _extract_transcript(td) -> str | list:
    """get_meeting_transcript returns JSON text — {"id", "title", "transcript":
    "<the whole transcript as one string>"} — which call_tool_data parses to a
    dict, so unwrap the inner string. A bare string (non-JSON tool output) or a
    segment list needs no unwrapping: _render_meeting renders both directly."""
    if isinstance(td, dict):
        td = td.get("transcript")
    if isinstance(td, str | list):
        return td
    return ""


# US timezone abbreviations in the list blob's date. strptime's %Z can't parse
# these portably, so the zone is split off and applied as an explicit offset.
_US_TZ_OFFSET_HOURS = {
    "PST": -8,
    "PDT": -7,
    "MST": -7,
    "MDT": -6,
    "CST": -6,
    "CDT": -5,
    "EST": -5,
    "EDT": -4,
}


def _meeting_time(meeting: dict) -> datetime | None:
    """The meeting's timestamp. Granola's MCP tool returns dates in three
    shapes — ISO-8601, "Jun 5, 2026", and "Jul 9, 2026 6:10 PM PDT" — so all
    parse; anything else yields None (the document shows no timestamp) rather
    than failing the sync."""
    when = meeting.get("date") or meeting.get("created_at") or meeting.get("start_time")
    if not when or not isinstance(when, str):
        return None
    when = when.strip()
    try:
        return datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError:
        pass
    date_part, _, zone = when.rpartition(" ")
    if zone in _US_TZ_OFFSET_HOURS:
        try:
            naive = datetime.strptime(date_part, "%b %d, %Y %I:%M %p")
        except ValueError:
            return None
        return naive.replace(tzinfo=timezone(timedelta(hours=_US_TZ_OFFSET_HOURS[zone])))
    try:
        return datetime.strptime(when, "%b %d, %Y")
    except ValueError:
        return None


def _meeting_path(meeting: dict, meeting_id: str) -> str:
    """Index path for a meeting: "YYYY-MM/DD title (id8)". Month folders group
    the calendar and the day prefix keeps each month chronological (path order
    is the VFS listing order); the id suffix disambiguates same-titled meetings.
    A meeting whose date didn't parse files under "undated/"."""
    title = " ".join((meeting.get("title") or "Untitled meeting").replace("/", "-").split())[:60]
    leaf = f"{title.strip()} ({meeting_id[:8]})"
    when = _meeting_time(meeting)
    if when is None:
        return f"undated/{leaf}"
    return f"{when:%Y-%m}/{when:%d} {leaf}"


def _render_meeting(meeting: dict, transcript) -> str:
    """A meeting's markdown: title + participants + the transcript. `transcript`
    may be a plain string (Granola returns text) or a list of segments."""
    title = meeting.get("title") or "Untitled meeting"
    lines = [f"# {title}", ""]

    when = meeting.get("date") or meeting.get("created_at") or meeting.get("start_time")
    if when:
        lines += [f"_{when}_", ""]

    participants = meeting.get("participants")
    if isinstance(participants, str) and participants.strip():
        lines += [f"**Participants:** {participants.strip()}", ""]
    else:
        attendees = meeting.get("attendees") or meeting.get("people") or []
        names = [
            a.get("name") or a.get("email") if isinstance(a, dict) else str(a) for a in attendees
        ]
        names = [n for n in names if n]
        if names:
            lines += [f"**Attendees:** {', '.join(names)}", ""]

    notes = meeting.get("notes") or meeting.get("summary")
    if notes:
        lines += [notes.strip(), ""]

    if isinstance(transcript, str) and transcript.strip():
        lines += ["## Transcript", "", transcript.strip()]
    elif isinstance(transcript, list) and transcript:
        lines += ["## Transcript", ""]
        for entry in transcript:
            text = (
                (entry.get("text") or "").strip() if isinstance(entry, dict) else str(entry).strip()
            )
            if not text:
                continue
            speaker = entry.get("speaker") if isinstance(entry, dict) else None
            lines.append(f"**{speaker or 'speaker'}:** {text}")

    return "\n".join(lines).strip()


async def index_granola(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])

    access_token = await get_valid_access_token(owner_user_id)
    present: list[str] = []

    # Transcripts are immutable once a meeting ends, and Granola rate-limits
    # transcript fetches hard — so only fetch for meetings whose stored doc
    # doesn't already carry one. Meetings that get rate-limited land with just
    # title + participants and pick up their transcript on a later sync.
    # Keyed by meeting id, not path: a title or date change moves the path,
    # and the stored transcript must move with it instead of being refetched.
    rows = await get_pool().fetch(
        "SELECT external_ref, path, content FROM granola_notes "
        "WHERE source_id = $1 AND content LIKE '%## Transcript%'",
        source_id,
    )
    stored_with_transcript = {r["external_ref"]: r for r in rows}

    async with granola_session(access_token) as session:
        tools = (await session.list_tools()).tools
        names = [t.name for t in tools]
        logger.info("granola source %s: discovered %d MCP tool(s)", source_id, len(names))

        list_tool = _pick_tool(names, _LIST_HINTS)
        if not list_tool:
            logger.warning("granola source %s: no meetings-list tool found", source_id)
            return None
        transcript_tool = _pick_tool([n for n in names if n != list_tool], _TRANSCRIPT_HINTS)

        # list_meetings defaults to last_30_days; anything older would then be
        # soft-deleted by remove_missing_documents on every sync. Ask for the
        # full history with an explicit wide range.
        data = await call_tool_data(
            session,
            list_tool,
            {"time_range": "custom", "custom_start": "2000-01-01", "custom_end": "2100-01-01"},
        )
        meetings = _parse_meetings_text(data) if isinstance(data, str) else []
        declared = _declared_meeting_count(data) if isinstance(data, str) else None
        logger.info(
            "granola source %s: parsed %d meeting(s) (declared %s)",
            source_id,
            len(meetings),
            declared,
        )
        # Only a listing we fully parsed may drive the delete-to-mirror sweep
        # below. Granola states its own count on the envelope: read exactly that
        # many and the response is genuine (0 = a truly empty account, honored);
        # read fewer, or find no envelope at all, and the response drifted under
        # us — fail loud and keep every stored note rather than delete to match
        # a response we did not understand (this exact mismatch wiped the archive
        # in 2026-08, when Granola added attributes our parser could not read).
        if declared is None or len(meetings) != declared:
            # Log the shape, never the content: attribute names reveal a tag
            # drift (the 2026-08 cause) without putting meeting titles or
            # participant emails in worker logs. Replay against a live token for
            # detail if the names are not enough.
            first_tag = _MEETING_BLOCK_RE.search(data) if isinstance(data, str) else None
            meeting_attrs = (
                sorted(dict(_ATTR_RE.findall(first_tag.group("attrs")))) if first_tag else []
            )
            logger.warning(
                "granola source %s: unreadable listing declared=%s parsed=%d type=%s meeting_attrs=%s",
                source_id,
                declared,
                len(meetings),
                type(data).__name__,
                meeting_attrs,
            )
            raise source_service.SourceSyncUserError(
                "Granola returned a response we could not fully read, so syncing is "
                "paused for this source to protect your saved notes. This is a bug on "
                "our side, not your account — nothing was deleted."
            )

        for meeting in meetings[:MAX_MEETINGS]:
            if not isinstance(meeting, dict):
                continue
            meeting_id = _meeting_id(meeting)
            if not meeting_id:
                continue
            path = _meeting_path(meeting, meeting_id)
            existing = stored_with_transcript.get(meeting_id)
            if existing is not None:
                if existing["path"] != path:
                    # The path moved (title/date change or path-scheme change):
                    # re-file the stored document instead of refetching it.
                    await source_service.upsert_content_document(
                        table="granola_notes",
                        source_id=source_id,
                        owner_user_id=owner_user_id,
                        path=path,
                        name=meeting.get("title") or "Untitled meeting",
                        kind="note",
                        content=existing["content"],
                        external_ref=meeting_id,
                        external_updated_at=_meeting_time(meeting),
                    )
                present.append(path)
                continue
            transcript = ""
            if transcript_tool:
                try:
                    td = await call_tool_data(session, transcript_tool, {"meeting_id": meeting_id})
                    transcript = _extract_transcript(td)
                except Exception as exc:
                    logger.info(
                        "granola transcript fetch failed source=%s exception_type=%s",
                        source_id,
                        type(exc).__name__,
                    )
            await source_service.upsert_content_document(
                table="granola_notes",
                source_id=source_id,
                owner_user_id=owner_user_id,
                path=path,
                name=meeting.get("title") or "Untitled meeting",
                kind="note",
                content=_render_meeting(meeting, transcript),
                external_ref=meeting_id,
                external_updated_at=_meeting_time(meeting),
            )
            present.append(path)

    # We only reach here after the listing fully parsed (declared == parsed
    # above), so an empty `present` means Granola reported an empty account, not
    # a broken response — the sweep mirrors that deletion.
    await source_service.remove_missing_documents("granola_notes", source_id, present)
    logger.info("granola source %s: indexed %d meeting(s)", source_id, len(present))
    return None
