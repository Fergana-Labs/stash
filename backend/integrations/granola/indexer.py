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
from uuid import UUID

from ...services import source_service
from .client import call_tool_json, granola_session
from .oauth import get_valid_access_token

logger = logging.getLogger(__name__)

# Granola rate-limits; a transcript fetch per meeting can add up, so cap a sync.
MAX_MEETINGS = 1000


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


def _render_meeting(meeting: dict, transcript: list) -> str:
    """A meeting's markdown: title + attendees + the speaker-labelled transcript."""
    title = meeting.get("title") or "Untitled meeting"
    lines = [f"# {title}", ""]

    when = meeting.get("date") or meeting.get("created_at") or meeting.get("start_time")
    if when:
        lines += [f"_{when}_", ""]

    attendees = meeting.get("attendees") or meeting.get("people") or []
    names = [a.get("name") or a.get("email") if isinstance(a, dict) else str(a) for a in attendees]
    names = [n for n in names if n]
    if names:
        lines += [f"**Attendees:** {', '.join(names)}", ""]

    notes = meeting.get("notes") or meeting.get("summary")
    if notes:
        lines += [notes.strip(), ""]

    if transcript:
        lines += ["## Transcript", ""]
        for entry in transcript:
            text = (
                (entry.get("text") or "").strip() if isinstance(entry, dict) else str(entry).strip()
            )
            if not text:
                continue
            speaker = entry.get("speaker") if isinstance(entry, dict) else None
            label = speaker or "speaker"
            lines.append(f"**{label}:** {text}")

    return "\n".join(lines).strip()


async def index_granola(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])

    access_token = await get_valid_access_token(owner_user_id)
    present: list[str] = []

    async with granola_session(access_token) as session:
        meetings_result = await call_tool_json(session, "list_meetings")
        meetings = _as_list(meetings_result, "meetings", "results", "items")

        for meeting in meetings[:MAX_MEETINGS]:
            meeting_id = _meeting_id(meeting)
            if not meeting_id:
                continue
            transcript_result = await call_tool_json(
                session, "get_meeting_transcript", {"meeting_id": meeting_id}
            )
            transcript = _as_list(transcript_result, "transcript", "segments", "entries")
            await source_service.upsert_content_document(
                table="granola_notes",
                source_id=source_id,
                workspace_id=workspace_id,
                path=meeting_id,
                name=meeting.get("title") or "Untitled meeting",
                kind="note",
                content=_render_meeting(meeting, transcript),
                external_ref=meeting_id,
            )
            present.append(meeting_id)

    await source_service.soft_delete_missing("granola_notes", source_id, present)
    logger.info("granola source %s: indexed %d meeting(s)", source_id, len(present))
    return None
