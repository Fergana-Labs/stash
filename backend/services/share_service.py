"""Share-link minting + recipient public projection (Phase 5)."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..config import settings
from ..database import get_pool


def _new_token() -> str:
    return secrets.token_urlsafe(16)  # 22 url-safe chars


async def create_link(
    *,
    stash_id: UUID,
    creator_id: UUID,
    ttl_days: int | None,
    permission: str,
) -> dict:
    pool = get_pool()
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days else None
    token = _new_token()
    row = await pool.fetchrow(
        "INSERT INTO share_links (token, workspace_id, created_by, expires_at, permission) "
        "VALUES ($1, $2, $3, $4, $5) "
        "RETURNING token, workspace_id, created_by, created_at, expires_at, permission, view_count",
        token,
        stash_id,
        creator_id,
        expires_at,
        permission,
    )
    out = dict(row)
    out["url"] = f"{settings.PUBLIC_URL.rstrip('/')}/share/{out['token']}"
    return out


async def list_links(stash_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT token, workspace_id, created_by, created_at, expires_at, permission, "
        "view_count, last_viewed_at FROM share_links "
        "WHERE workspace_id = $1 AND revoked_at IS NULL ORDER BY created_at DESC",
        stash_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["url"] = f"{settings.PUBLIC_URL.rstrip('/')}/share/{d['token']}"
        out.append(d)
    return out


async def revoke_link(token: str, stash_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "UPDATE share_links SET revoked_at = now() "
        "WHERE token = $1 AND workspace_id = $2 AND revoked_at IS NULL",
        token,
        stash_id,
    )
    return result.endswith(" 1")


async def resolve_token(token: str) -> dict | None:
    """Returns (link_row, status). status: 'ok' | 'expired' | 'revoked' | 'missing'.

    Caller should 410 on expired/revoked, 404 on missing.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT token, workspace_id, created_by, created_at, expires_at, permission, "
        "view_count, revoked_at FROM share_links WHERE token = $1",
        token,
    )
    if not row:
        return {"status": "missing"}
    if row["revoked_at"]:
        return {"status": "revoked"}
    if row["expires_at"] and row["expires_at"] < datetime.now(UTC):
        return {"status": "expired"}
    return {"status": "ok", "link": dict(row)}


async def record_view(token: str, viewer_user_id: UUID | None) -> None:
    pool = get_pool()
    await pool.execute(
        "UPDATE share_links "
        "SET view_count = view_count + 1, last_viewed_at = now(), last_viewed_by = $2 "
        "WHERE token = $1",
        token,
        viewer_user_id,
    )


_SLIDE_SPLIT = re.compile(r"^\s*---+\s*$", re.MULTILINE)


def _parse_deck(narrative_md: str) -> list[dict] | None:
    """A narrative becomes a deck if it has 2+ horizontal-rule-separated slide
    blocks. Each block's leading H1 is the slide title; the rest is body."""
    if not narrative_md:
        return None
    parts = [p.strip() for p in _SLIDE_SPLIT.split(narrative_md) if p.strip()]
    if len(parts) < 2:
        return None
    slides = []
    for i, part in enumerate(parts):
        lines = part.splitlines()
        title = ""
        body_lines = lines
        for j, ln in enumerate(lines):
            stripped = ln.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                body_lines = lines[j + 1 :]
                break
        slides.append(
            {
                "index": i,
                "title": title or f"Slide {i + 1}",
                "kicker": f"{i + 1:02d} / {len(parts):02d}",
                "body": "\n".join(body_lines).strip(),
            }
        )
    return slides


async def public_projection(stash_id: UUID, link: dict) -> dict:
    """The view a recipient gets. Pulls only resources flagged public_in_share
    plus the stash narrative (if any)."""
    pool = get_pool()
    stash = await pool.fetchrow(
        "SELECT id, name, description, summary, cover_image_url, creator_id, created_at "
        "FROM workspaces WHERE id = $1",
        stash_id,
    )
    if not stash:
        return {}
    creator = await pool.fetchrow(
        "SELECT name, display_name FROM users WHERE id = $1", stash["creator_id"]
    )

    # Narrative = page named 'Narrative.md' or any page flagged public_in_share
    # whose name suggests a deck.
    narrative_row = await pool.fetchrow(
        "SELECT id, name, content_markdown FROM pages "
        "WHERE workspace_id = $1 AND (name = 'Narrative.md' OR public_in_share = TRUE) "
        "ORDER BY (name = 'Narrative.md') DESC, updated_at DESC LIMIT 1",
        stash_id,
    )
    narrative = dict(narrative_row) if narrative_row else None

    pages = await pool.fetch(
        "SELECT id, name, content_markdown, updated_at FROM pages "
        "WHERE workspace_id = $1 AND public_in_share = TRUE ORDER BY name",
        stash_id,
    )
    files = await pool.fetch(
        "SELECT id, name, content_type, size_bytes, created_at FROM files "
        "WHERE workspace_id = $1 AND public_in_share = TRUE ORDER BY created_at DESC",
        stash_id,
    )

    deck = _parse_deck(narrative["content_markdown"]) if narrative else None

    return {
        "stash": {
            "id": str(stash["id"]),
            "name": stash["name"],
            "description": stash["description"],
            "summary": stash["summary"],
            "cover_image_url": stash["cover_image_url"],
            "creator": {
                "name": creator["name"] if creator else "—",
                "display_name": creator["display_name"] if creator else None,
            },
        },
        "share": {
            "token": link["token"],
            "permission": link["permission"],
            "expires_at": link["expires_at"],
            "view_count": link["view_count"],
            "created_at": link["created_at"],
        },
        "narrative": (
            {
                "id": str(narrative["id"]),
                "name": narrative["name"],
                "body": narrative["content_markdown"] or "",
            }
            if narrative
            else None
        ),
        "deck": deck,
        "pages": [
            {
                "id": str(p["id"]),
                "name": p["name"],
                "body": p["content_markdown"] or "",
            }
            for p in pages
        ],
        "files": [
            {
                "id": str(f["id"]),
                "name": f["name"],
                "content_type": f["content_type"],
                "size_bytes": f["size_bytes"],
            }
            for f in files
        ],
    }
