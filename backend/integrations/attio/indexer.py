"""Attio → attio_documents indexer (copied content; FTS-searchable).

One Attio connection = one source (external_ref "calls"). We page meetings from
a rolling window (last LOOKBACK_DAYS), then for each meeting pull its call
recordings and each recording's transcript, and write every recording as a text
document (title + date + speaker-labelled transcript). Idempotent re-sync via
source_service; recordings that age out of the window are soft-deleted.

Attio ids are composite ({workspace_id, meeting_id, call_recording_id}); the
URL path segments are the bare uuids. The recording is keyed by
call_recording_id, which is unique across meetings.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token

logger = logging.getLogger(__name__)

BASE_URL = "https://api.attio.com"
LOOKBACK_DAYS = 90
MAX_MEETINGS = 5000
PAGE_LIMIT = 200


def _parse_time(value: str | None) -> datetime | None:
    """Attio returns ISO-8601 ('...Z'); the column is timestamptz. A recording
    never changes after the call, so its creation time is its modified time."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _render_call(title: str, created_at: str, transcript: list[dict]) -> str:
    lines = [f"# {title}", f"Date: {created_at}", ""]
    speaker_num: dict[str, int] = {}
    for segment in transcript:
        name = (segment.get("speaker") or {}).get("name") or "?"
        if name not in speaker_num:
            speaker_num[name] = len(speaker_num) + 1
        speech = (segment.get("speech") or "").strip()
        if speech:
            lines.append(f"[Speaker {speaker_num[name]}]: {speech}")
    return "\n".join(lines)


async def _fetch_meetings(client: httpx.AsyncClient, ends_from: str) -> list[dict]:
    meetings: list[dict] = []
    cursor: str | None = None
    while len(meetings) < MAX_MEETINGS:
        params = {"limit": PAGE_LIMIT, "sort": "start_desc", "ends_from": ends_from}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get("/v2/meetings", params=params)
        resp.raise_for_status()
        payload = resp.json()
        meetings.extend(payload.get("data", []))
        cursor = (payload.get("pagination") or {}).get("next_cursor")
        if not cursor:
            break
    return meetings


async def _fetch_recordings(client: httpx.AsyncClient, meeting_id: str) -> list[dict]:
    recordings: list[dict] = []
    cursor: str | None = None
    while True:
        params = {"limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(f"/v2/meetings/{meeting_id}/call_recordings", params=params)
        resp.raise_for_status()
        payload = resp.json()
        recordings.extend(payload.get("data", []))
        cursor = (payload.get("pagination") or {}).get("next_cursor")
        if not cursor:
            break
    return recordings


async def _fetch_transcript(
    client: httpx.AsyncClient, meeting_id: str, recording_id: str
) -> list[dict]:
    segments: list[dict] = []
    cursor: str | None = None
    while True:
        params = {"limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(
            f"/v2/meetings/{meeting_id}/call_recordings/{recording_id}/transcript",
            params=params,
        )
        resp.raise_for_status()
        payload = resp.json()
        segments.extend((payload.get("data") or {}).get("transcript", []))
        cursor = (payload.get("pagination") or {}).get("next_cursor")
        if not cursor:
            break
    return segments


async def index_attio(source: dict) -> str | None:
    source_id = UUID(source["id"])
    owner_user_id = UUID(source["owner_user_id"])
    token = await get_valid_token(owner_user_id, "attio")
    headers = {"Authorization": f"Bearer {token}"}
    ends_from = (datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)).isoformat()

    present: list[str] = []
    async with httpx.AsyncClient(timeout=120.0, headers=headers, base_url=BASE_URL) as client:
        meetings = await _fetch_meetings(client, ends_from)
        for meeting in meetings:
            meeting_id = meeting["id"]["meeting_id"]
            title = meeting.get("title") or "Untitled call"
            for recording in await _fetch_recordings(client, meeting_id):
                recording_id = recording["id"]["call_recording_id"]
                created_at = recording.get("created_at") or ""
                transcript = await _fetch_transcript(client, meeting_id, recording_id)
                await source_service.upsert_content_document(
                    table="attio_documents",
                    source_id=source_id,
                    owner_user_id=owner_user_id,
                    path=recording_id,
                    name=title,
                    kind="call",
                    content=_render_call(title, created_at, transcript),
                    external_ref=recording_id,
                    external_updated_at=_parse_time(created_at),
                )
                present.append(recording_id)

    await source_service.remove_missing_documents("attio_documents", source_id, present)
    logger.info("attio source %s: indexed %d recording(s)", source_id, len(present))
    return None
