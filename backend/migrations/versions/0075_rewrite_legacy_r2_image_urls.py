"""Rewrite legacy presigned R2 URLs in page bodies to the stable proxy.

Before commit a5d56036 ("Fix public Stash markdown image rendering"),
the workspace page editor inserted raw presigned R2 URLs into
``pages.content_markdown`` / ``content_html``. Those URLs carry
``X-Amz-Expires=3600`` — once an hour passes the image stops loading
forever, so every page authored before that fix has dead images today.

This migration finds every presigned R2 URL in page bodies, looks up the
matching ``files.id`` by ``storage_key``, and rewrites the URL to the
stable proxy form ``/api/v1/workspaces/{wid}/files/{fid}/download``.

Revision ID: 0075
Revises: 0074
Create Date: 2026-05-21
"""

import logging
import re
from urllib.parse import unquote

from alembic import op
from sqlalchemy import text

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

# Matches:
#   https://<host>.r2.cloudflarestorage.com/<bucket>/<workspace_id>/<12hex>/<filename>?<query>
# Capture groups:
#   1: workspace_id/12hex/filename  (= storage_key, may be percent-encoded)
# The query string (anything after `?`) is consumed by the trailing
# `[^)\s"']*` so we strip the expired signature along with the rest.
_R2_URL_RE = re.compile(
    r"""https://[^/\s)"']+\.r2\.cloudflarestorage\.com/[^/\s)"']+/"""
    r"""([^?\s)"']+)"""
    r"""(?:\?[^)\s"']*)?""",
)


def _rewrite_body(body: str, lookup_file_id) -> str:
    def replace(match: re.Match[str]) -> str:
        encoded_key = match.group(1)
        storage_key = unquote(encoded_key)
        file_id = lookup_file_id(storage_key)
        if not file_id:
            return match.group(0)
        workspace_id = storage_key.split("/", 1)[0]
        return f"/api/v1/workspaces/{workspace_id}/files/{file_id}/download"

    return _R2_URL_RE.sub(replace, body)


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(text("""
            SELECT id, content_markdown, content_html
            FROM pages
            WHERE content_markdown LIKE '%r2.cloudflarestorage.com%'
               OR content_html LIKE '%r2.cloudflarestorage.com%'
            """)).fetchall()

    if not rows:
        return

    file_id_cache: dict[str, str | None] = {}

    def lookup_file_id(storage_key: str) -> str | None:
        if storage_key in file_id_cache:
            return file_id_cache[storage_key]
        result = bind.execute(
            text("SELECT id FROM files WHERE storage_key = :sk"),
            {"sk": storage_key},
        ).fetchone()
        file_id = str(result[0]) if result else None
        file_id_cache[storage_key] = file_id
        return file_id

    updated = 0
    for row in rows:
        page_id, md, html = row[0], row[1] or "", row[2] or ""
        new_md = _rewrite_body(md, lookup_file_id)
        new_html = _rewrite_body(html, lookup_file_id)
        if new_md == md and new_html == html:
            continue
        bind.execute(
            text("""
                UPDATE pages
                SET content_markdown = :md,
                    content_html = :html,
                    updated_at = now()
                WHERE id = :id
                """),
            {"md": new_md, "html": new_html, "id": page_id},
        )
        updated += 1

    logger.info("0075: rewrote presigned R2 URLs in %d pages", updated)


def downgrade() -> None:
    # Irreversible: the original presigned URLs are expired and worthless.
    pass
