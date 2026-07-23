"""The home-page feed: one continuous stream of community skills to copy,
fresh public pages, and — for a signed-in user — resurfaced items from their
own stash (clips and X/Instagram saves old enough to be worth re-encountering).

Interleave happens server-side so the client renders a flat list. Resurface
selection is deterministic per (user, day): an md5 sort seeded by user id +
date gives the same sample all day and a fresh one tomorrow, without storing
any state.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from ..database import get_pool
from ..integrations.social_saves.indexer import post_url
from ..integrations.x_saves.indexer import tweet_url
from . import paste_service, shared_skill_service, storage_service
from .clip_service import CLIPS_FOLDER, RAW_FOLDER

PAGE_SKILLS = 6
PAGE_PUBLIC_PAGES = 3
PAGE_RESURFACE = 3
# Only items past this age resurface — the feed re-encounters the archive,
# it doesn't echo what the user just saved.
RESURFACE_MIN_AGE_DAYS = 7
PREVIEW_CHARS = 280


async def home_feed(user_id: UUID | None, cursor: int) -> dict:
    skills = await shared_skill_service.list_public_skills(
        sort="trending", limit=PAGE_SKILLS, offset=cursor * PAGE_SKILLS
    )
    pages = await paste_service.list_recent(
        limit=PAGE_PUBLIC_PAGES, offset=cursor * PAGE_PUBLIC_PAGES
    )
    resurfaced = await _resurface_items(user_id, cursor) if user_id else []
    has_more = (
        len(skills) == PAGE_SKILLS
        or len(pages) == PAGE_PUBLIC_PAGES
        or len(resurfaced) == PAGE_RESURFACE
    )
    return {
        "items": _interleave(skills, pages, resurfaced),
        "next_cursor": cursor + 1 if has_more else None,
    }


def _interleave(skills: list[dict], pages: list[dict], resurfaced: list[dict]) -> list[dict]:
    """Flat feed order: two skills per public page in the community stream,
    with a resurface card landing every 4th slot."""
    community: list[dict] = []
    si, pi = 0, 0
    while si < len(skills) or pi < len(pages):
        for _ in range(2):
            if si < len(skills):
                community.append({"kind": "skill", "data": skills[si]})
                si += 1
        if pi < len(pages):
            community.append({"kind": "public_page", "data": pages[pi]})
            pi += 1

    items: list[dict] = []
    ci, ri = 0, 0
    while ci < len(community) or ri < len(resurfaced):
        resurface_slot = len(items) % 4 == 3
        if ri < len(resurfaced) and (resurface_slot or ci >= len(community)):
            items.append({"kind": "resurface", "data": resurfaced[ri]})
            ri += 1
        else:
            items.append(community[ci])
            ci += 1
    return items


async def _resurface_items(user_id: UUID, cursor: int) -> list[dict]:
    seed = f"{user_id}:{datetime.now(UTC).date().isoformat()}:"
    rows = await get_pool().fetch(
        f"""
        WITH pool AS (
            SELECT 'x' AS source, id::text AS item_id, name AS title, content,
                   created_at, external_ref, NULL::uuid AS page_id,
                   media->0->>'storage_key' AS media_key
            FROM x_save_docs
            WHERE owner_user_id = $1 AND hydration_status = 'done'
              AND deleted_at IS NULL AND content IS NOT NULL
              AND created_at < now() - interval '{RESURFACE_MIN_AGE_DAYS} days'
            UNION ALL
            SELECT 'instagram', id::text, name, content,
                   created_at, external_ref, NULL::uuid, media_storage_key
            FROM instagram_save_docs
            WHERE owner_user_id = $1 AND hydration_status = 'done'
              AND deleted_at IS NULL AND content IS NOT NULL
              AND created_at < now() - interval '{RESURFACE_MIN_AGE_DAYS} days'
            UNION ALL
            SELECT 'clip', p.id::text, p.name,
                   coalesce(p.content_markdown, p.content_html),
                   p.created_at, NULL, p.id, NULL
            FROM pages p
            JOIN folders raw_f ON p.folder_id = raw_f.id AND raw_f.name = $4
            JOIN folders clips_f ON raw_f.parent_folder_id = clips_f.id
                 AND clips_f.name = $5 AND clips_f.parent_folder_id IS NULL
            WHERE p.owner_user_id = $1 AND p.deleted_at IS NULL
              AND p.created_at < now() - interval '{RESURFACE_MIN_AGE_DAYS} days'
        )
        SELECT * FROM pool ORDER BY md5($2::text || item_id) LIMIT $3 OFFSET $6
        """,
        user_id,
        seed,
        PAGE_RESURFACE,
        RAW_FOLDER,
        CLIPS_FOLDER,
        cursor * PAGE_RESURFACE,
    )
    return [await _resurface_card(dict(r)) for r in rows]


async def _resurface_card(row: dict) -> dict:
    source = row["source"]
    if source == "x":
        app_url = None
        external_url = tweet_url(row["external_ref"])
    elif source == "instagram":
        app_url = None
        external_url = post_url(row["external_ref"])
    else:
        app_url = f"/p/{row['page_id']}"
        external_url = None

    image_url = None
    if row["media_key"] and storage_service.is_configured():
        image_url = await storage_service.get_file_url(row["media_key"])

    return {
        "source": source,
        "title": row["title"],
        "preview": _preview(row["content"]),
        "saved_at": row["created_at"].isoformat(),
        "app_url": app_url,
        "external_url": external_url,
        "image_url": image_url,
    }


def _preview(content: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", content or "")
    return re.sub(r"\s+", " ", text).strip()[:PREVIEW_CHARS]
