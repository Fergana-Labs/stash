"""Granola → granola_notes indexer (scheduled pull, via the MCP server).

Opens an MCP session to Granola (bearer token, refreshed on demand) and pulls
meetings with `list_meetings`, then each meeting's transcript with
`get_meeting_transcript`. Each meeting's rendered markdown lands in granola_notes
(FTS + embeddings), keyed by meeting id. Idempotent re-sync is handled upstream
(content-hash dedupe + soft-delete of vanished meetings).

Note: the exact JSON field names returned by Granola's MCP tools are only
visible from an authenticated `tools/list`, so the small parse helpers below
(`_meeting_id`, `_render_meeting`) encode the documented shape and are the one
spot to adjust against a live account.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

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


def _as_list(result, *keys) -> list:
    """MCP tools may return a bare list or wrap it under a key — accept both."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if isinstance(value, list):
                return value
    return []


def _meeting_id(meeting: dict) -> str | None:
    return meeting.get("id") or meeting.get("meeting_id") or meeting.get("document_id")


# Granola's list_meetings returns an XML-ish text blob (not JSON):
#   <meetings_data ...><meeting id=".." title=".." date="..">…</meeting>…
# It isn't valid XML (participant emails contain raw <>), so parse with a regex.
_MEETING_RE = re.compile(
    r'<meeting\s+id="(?P<id>[^"]+)"\s+title="(?P<title>[^"]*)"\s+date="(?P<date>[^"]*)"\s*>'
    r"(?P<body>.*?)</meeting>",
    re.DOTALL,
)


def _parse_meetings_text(text: str) -> list[dict]:
    meetings = []
    for m in _MEETING_RE.finditer(text):
        body = m.group("body")
        participants = re.sub(r"</?known_participants>", "", body)
        participants = " ".join(participants.split())
        meetings.append(
            {
                "id": m.group("id"),
                "title": m.group("title") or "Untitled meeting",
                "date": m.group("date"),
                "participants": participants,
            }
        )
    return meetings


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
    owner_user_id = UUID(source["owner_user_id"])

    access_token = await get_valid_access_token(owner_user_id)
    present: list[str] = []

    async with granola_session(access_token) as session:
        tools = (await session.list_tools()).tools
        names = [t.name for t in tools]
        logger.info("granola source %s: discovered %d MCP tool(s)", source_id, len(names))

        list_tool = _pick_tool(names, _LIST_HINTS)
        if not list_tool:
            logger.warning("granola source %s: no meetings-list tool found", source_id)
            return None
        transcript_tool = _pick_tool([n for n in names if n != list_tool], _TRANSCRIPT_HINTS)

        data = await call_tool_data(session, list_tool, {"limit": MAX_MEETINGS})
        # Granola returns an XML-ish text blob; other shapes (JSON list/dict) are
        # handled too for resilience.
        if isinstance(data, str):
            meetings = _parse_meetings_text(data)
        else:
            meetings = _as_list(data, "meetings", "results", "items", "documents", "notes", "data")
        logger.info("granola source %s: listed %d meeting(s)", source_id, len(meetings))

        for meeting in meetings[:MAX_MEETINGS]:
            if not isinstance(meeting, dict):
                continue
            meeting_id = _meeting_id(meeting)
            if not meeting_id:
                continue
            transcript = ""
            if transcript_tool:
                try:
                    td = await call_tool_data(session, transcript_tool, {"meeting_id": meeting_id})
                    transcript = (
                        td
                        if isinstance(td, str)
                        else _as_list(td, "transcript", "segments", "entries")
                    )
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
                path=meeting_id,
                name=meeting.get("title") or "Untitled meeting",
                kind="note",
                content=_render_meeting(meeting, transcript),
                external_ref=meeting_id,
            )
            present.append(meeting_id)

    await source_service.remove_missing_documents("granola_notes", source_id, present)
    logger.info("granola source %s: indexed %d meeting(s)", source_id, len(present))
    return None
