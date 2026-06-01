"""Granola → source_documents indexer (scheduled pull).

Lists the workspace's notes and upserts each (title + content + transcript) as a
searchable document. Idempotent re-sync is handled upstream (content-hash dedupe
+ soft-delete of vanished notes).

NOTE: the notes/transcript endpoint shapes below must be confirmed against
docs.granola.ai. The indexer is inert until a Granola source is connected.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from ...services import source_service
from ..storage import get_valid_token
from .provider import API_BASE

logger = logging.getLogger(__name__)

NOTES_URL = f"{API_BASE}/notes"
MAX_NOTES = 1000


async def index_granola(source: dict) -> str | None:
    source_id = UUID(source["id"])
    workspace_id = UUID(source["workspace_id"])
    owner_user_id = UUID(source["owner_user_id"])

    token = await get_valid_token(owner_user_id, "granola")
    headers = {"Authorization": f"Bearer {token}"}
    present: list[str] = []

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        cursor: str | None = None
        while len(present) < MAX_NOTES:
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get(NOTES_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
            for note in payload.get("notes", payload.get("data", [])):
                note_id = note.get("id")
                if not note_id:
                    continue
                title = note.get("title") or "Untitled note"
                body = note.get("content") or note.get("notes") or ""
                transcript = note.get("transcript") or ""
                content = f"# {title}\n\n{body}\n\n{transcript}".strip()
                await source_service.upsert_document(
                    source_id=source_id,
                    workspace_id=workspace_id,
                    path=f"{note_id}",
                    name=title,
                    kind="note",
                    content=content,
                    external_ref=note_id,
                )
                present.append(f"{note_id}")
            cursor = payload.get("next_cursor")
            if not cursor:
                break

    await source_service.soft_delete_missing(source_id, present)
    logger.info("granola source %s: indexed %d note(s)", source_id, len(present))
    return None
