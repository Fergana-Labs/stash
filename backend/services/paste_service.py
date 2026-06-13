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
    "slug, title, content_type, content, visibility, comments_enabled, "
    "view_count, created_at, updated_at"
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


async def authorize_collab(slug: str, token: str) -> dict | None:
    """Resolve a paste for a live-editing socket: valid edit token plus
    markdown content (HTML pages don't have collab, same as the app)."""
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT id FROM pastes
        WHERE slug = $1 AND edit_token = $2 AND content_type = 'markdown'
        """,
        slug,
        token,
    )
    return dict(row) if row else None


async def update_paste(
    slug: str,
    token: str,
    title: str,
    content: str,
    comments_enabled: bool | None,
) -> dict | None:
    """None means unknown slug *or* bad token — callers 404 both, no token oracle.

    Empty title/content and a None comments_enabled mean "keep as is", so
    the settings toggle and content saves share this one write path.
    """
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        UPDATE pastes
        SET content = COALESCE(NULLIF($1, ''), content),
            title = COALESCE(NULLIF($2, ''), title),
            comments_enabled = COALESCE($3, comments_enabled),
            updated_at = now()
        WHERE slug = $4 AND edit_token = $5
        RETURNING id, {_PUBLIC_COLS}
        """,
        content,
        title.strip(),
        comments_enabled,
        slug,
        token,
    )
    if not row:
        return None
    paste = dict(row)
    if content:
        # A content write makes any persisted Y.Doc state stale — an agent
        # PATCH would otherwise be silently reverted the next time someone
        # opens the live editor. Live sessions are unaffected (the doc is
        # in collab-server memory and re-persists on its own debounce).
        await pool.execute("DELETE FROM paste_collab_documents WHERE paste_id = $1", paste["id"])
    paste.pop("id")
    return paste


async def delete_paste(slug: str, token: str) -> bool:
    """True when a paste matched slug+token and was deleted. Comments and
    collab state cascade via their FK ON DELETE CASCADE."""
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM pastes WHERE slug = $1 AND edit_token = $2",
        slug,
        token,
    )
    return result.endswith(" 1")


_COMMENT_COLS = "id, parent_id, author_name, body, quoted_text, prefix, suffix, created_at"


async def add_comment(
    slug: str,
    author_name: str,
    body: str,
    quoted_text: str,
    prefix: str,
    suffix: str,
    parent_id: str | None = None,
) -> dict | None:
    """None means the paste doesn't exist (or parent_id isn't a comment on
    it). The returned dict includes the comment's own edit_token — the only
    time it's exposed."""
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        INSERT INTO paste_comments
            (paste_id, parent_id, author_name, body, quoted_text, prefix, suffix, edit_token)
        SELECT p.id, $8::uuid, $2, $3, $4, $5, $6, $7
        FROM pastes p
        WHERE p.slug = $1
          AND ($8::uuid IS NULL OR EXISTS (
            SELECT 1 FROM paste_comments parent
            WHERE parent.id = $8::uuid AND parent.paste_id = p.id
          ))
        RETURNING edit_token, {_COMMENT_COLS}
        """,
        slug,
        author_name.strip(),
        body,
        quoted_text,
        prefix,
        suffix,
        secrets.token_urlsafe(16),
        parent_id,
    )
    return dict(row) if row else None


async def update_comment(slug: str, comment_id: str, token: str, body: str) -> dict | None:
    """Edit a comment's body — only its author (the comment's edit_token).
    None means not-found-or-bad-token."""
    pool = get_pool()
    # Qualify the RETURNING columns: id/created_at exist on both tables, so
    # they're ambiguous in an UPDATE...FROM without the alias.
    returning = ", ".join(f"c.{col.strip()}" for col in _COMMENT_COLS.split(","))
    row = await pool.fetchrow(
        f"""
        UPDATE paste_comments c
        SET body = $4
        FROM pastes p
        WHERE c.id = $2 AND c.paste_id = p.id AND p.slug = $1 AND c.edit_token = $3
        RETURNING {returning}
        """,
        slug,
        comment_id,
        token,
        body,
    )
    return dict(row) if row else None


async def delete_comment(slug: str, comment_id: str, token: str) -> bool:
    """True when deleted. Authorized by the comment's own edit_token (author)
    or the parent paste's edit_token (page owner moderation)."""
    pool = get_pool()
    result = await pool.execute(
        """
        DELETE FROM paste_comments c
        USING pastes p
        WHERE c.id = $2 AND c.paste_id = p.id AND p.slug = $1
          AND ($3 = c.edit_token OR $3 = p.edit_token)
        """,
        slug,
        comment_id,
        token,
    )
    return result.endswith(" 1")


async def list_comments(slug: str) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT {_COMMENT_COLS} FROM paste_comments
        WHERE paste_id = (SELECT id FROM pastes WHERE slug = $1)
        ORDER BY created_at
        """,
        slug,
    )
    return [dict(r) for r in rows]


async def list_recent(limit: int = 20, offset: int = 0) -> list[dict]:
    """Public pages ranked HN-style: views buoy a page, age sinks it.
    Paginated by offset so the feed never loads everything at once."""
    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT {_FEED_COLS} FROM pastes
        WHERE visibility = 'public'
        ORDER BY (view_count + 1)
                 / POWER(EXTRACT(EPOCH FROM (now() - created_at)) / 3600 + 2, 1.5)
                 DESC,
                 created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return [dict(r) for r in rows]
