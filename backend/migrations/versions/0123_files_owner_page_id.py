"""Embedded files: files.owner_page_id.

Images pasted into a page were uploaded with no owner at all, so every
screenshot landed at the root of the files tree while the page that embeds
it only held a `/api/v1/me/files/{id}/download` URL string. A file is now
either *filed* (folder or root, a tree entry) or *embedded* (owned by the
page whose body links it, absent from tree views) — never both, enforced by
the files_filed_or_embedded CHECK. Embedding is derived from page bodies on
every save; this backfill seeds it: for every live page, extract the file
ids referenced by its body and attach each still-root, still-unowned file
to the earliest page that references it.

Revision ID: 0123
Revises: 0122
Create Date: 2026-07-04
"""

import logging
import re

from alembic import op
from sqlalchemy import text

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

_DOWNLOAD_URL_RE = re.compile(
    r"/api/v1/me/files/"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"/download"
)


def upgrade() -> None:
    # ON DELETE CASCADE is a backstop for bulk cascades (user deletion);
    # the trash flow purges embedded files explicitly so blobs get cleaned up.
    op.execute(
        "ALTER TABLE files ADD COLUMN owner_page_id UUID REFERENCES pages(id) ON DELETE CASCADE"
    )
    op.execute("CREATE INDEX idx_files_owner_page ON files(owner_page_id)")

    bind = op.get_bind()
    pages = bind.execute(
        text(
            "SELECT id, owner_user_id, content_markdown, content_html FROM pages "
            "WHERE deleted_at IS NULL "
            "AND (content_markdown LIKE '%/download%' OR content_html LIKE '%/download%') "
            "ORDER BY created_at"
        )
    ).fetchall()

    # Earliest referencing page claims the file; later references are treated
    # as links to another page's embedded file.
    claims: dict[str, tuple] = {}
    for page in pages:
        page_id, owner_user_id, md, html = page[0], page[1], page[2] or "", page[3] or ""
        for match in _DOWNLOAD_URL_RE.finditer(f"{md}\n{html}"):
            claims.setdefault(match.group(1).lower(), (page_id, owner_user_id))

    embedded = 0
    for file_id, (page_id, owner_user_id) in claims.items():
        result = bind.execute(
            text(
                "UPDATE files SET owner_page_id = :page_id "
                "WHERE id = CAST(:file_id AS uuid) AND owner_user_id = :owner_user_id "
                "AND folder_id IS NULL AND owner_page_id IS NULL AND deleted_at IS NULL"
            ),
            {"page_id": page_id, "file_id": file_id, "owner_user_id": owner_user_id},
        )
        embedded += result.rowcount

    op.execute(
        "ALTER TABLE files ADD CONSTRAINT files_filed_or_embedded "
        "CHECK (folder_id IS NULL OR owner_page_id IS NULL)"
    )
    logger.info("0123: embedded %d root files into the pages that reference them", embedded)


def downgrade() -> None:
    op.execute("ALTER TABLE files DROP CONSTRAINT IF EXISTS files_filed_or_embedded")
    op.execute("DROP INDEX IF EXISTS idx_files_owner_page")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS owner_page_id")
