"""Anonymous public pastes backing the joinstash.ai/pages pastebin.

No accounts, no workspaces: the slug is the public read handle and the
plaintext ``edit_token`` is the only write credential. The token is
returned exactly once (from create) and never selected back out, so a
leaked read response can't grant write access.
"""

import re
import secrets

from ..database import get_pool

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_HTML_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_TITLE_MAX = 80

_PUBLIC_COLS = (
    "slug, title, content_type, content, visibility, view_count, created_at, updated_at"
)
_FEED_COLS = "slug, title, content_type, view_count, created_at"


def _slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", title.lower()).strip("-")[:64] or "paste"
    return f"{base}-{secrets.token_urlsafe(4)[:6].lower()}"


def _derive_title(content: str, content_type: str) -> str:
    if content_type == "html":
        match = _HTML_TITLE_RE.search(content) or _HTML_H1_RE.search(content)
        if match:
            text = " ".join(_HTML_TAG_RE.sub(" ", match.group(1)).split())
            if text:
                return text[:_TITLE_MAX]
        return "Untitled"
    for line in content.splitlines():
        text = line.lstrip("#").strip()
        if text:
            return text[:_TITLE_MAX]
    return "Untitled"


async def create_paste(title: str, content: str, content_type: str, visibility: str) -> dict:
    pool = get_pool()
    final_title = title.strip() or _derive_title(content, content_type)
    row = await pool.fetchrow(
        f"""
        INSERT INTO pastes (slug, edit_token, title, content_type, content, visibility)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING edit_token, {_PUBLIC_COLS}
        """,
        _slugify(final_title),
        secrets.token_urlsafe(16),
        final_title,
        content_type,
        content,
        visibility,
    )
    return dict(row)


async def get_paste(slug: str) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        UPDATE pastes SET view_count = view_count + 1
        WHERE slug = $1
        RETURNING {_PUBLIC_COLS}
        """,
        slug,
    )
    return dict(row) if row else None


async def update_paste(slug: str, token: str, title: str, content: str) -> dict | None:
    """None means unknown slug *or* bad token — callers 404 both, no token oracle."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        UPDATE pastes
        SET content = $1,
            title = COALESCE(NULLIF($2, ''), title),
            updated_at = now()
        WHERE slug = $3 AND edit_token = $4
        RETURNING {_PUBLIC_COLS}
        """,
        content,
        title.strip(),
        slug,
        token,
    )
    return dict(row) if row else None


async def list_recent(limit: int = 30) -> list[dict]:
    """Public pages ranked HN-style: views buoy a page, age sinks it."""
    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT {_FEED_COLS} FROM pastes
        WHERE visibility = 'public'
        ORDER BY (view_count + 1)
                 / POWER(EXTRACT(EPOCH FROM (now() - created_at)) / 3600 + 2, 1.5)
                 DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]
