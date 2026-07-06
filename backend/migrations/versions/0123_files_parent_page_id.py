"""Give files a real owning page: files.parent_page_id.

Images pasted into a page were uploaded with no parent at all, so every
screenshot landed at the root of the files tree while the page that embeds
it only held a `/api/v1/me/files/{id}/download` URL string. A file now has
exactly one parent — a folder OR a page (CHECK constraint) — and attachments
disappear from tree views: the page's embed link is the only reference.

Backfill: for every live page, extract the file ids referenced by its body
and attach each still-root, still-unattached file to the earliest page that
references it.

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
    # the trash flow purges attachments explicitly so blobs get cleaned up.
    op.execute(
        "ALTER TABLE files ADD COLUMN parent_page_id UUID REFERENCES pages(id) ON DELETE CASCADE"
    )
    op.execute("CREATE INDEX idx_files_parent_page ON files(parent_page_id)")

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
    # as links to another page's attachment.
    claims: dict[str, tuple] = {}
    for page in pages:
        page_id, owner_user_id, md, html = page[0], page[1], page[2] or "", page[3] or ""
        for match in _DOWNLOAD_URL_RE.finditer(f"{md}\n{html}"):
            claims.setdefault(match.group(1).lower(), (page_id, owner_user_id))

    attached = 0
    for file_id, (page_id, owner_user_id) in claims.items():
        result = bind.execute(
            text(
                "UPDATE files SET parent_page_id = :page_id "
                "WHERE id = CAST(:file_id AS uuid) AND owner_user_id = :owner_user_id "
                "AND folder_id IS NULL AND parent_page_id IS NULL AND deleted_at IS NULL"
            ),
            {"page_id": page_id, "file_id": file_id, "owner_user_id": owner_user_id},
        )
        attached += result.rowcount

    op.execute(
        "ALTER TABLE files ADD CONSTRAINT files_single_parent "
        "CHECK (folder_id IS NULL OR parent_page_id IS NULL)"
    )
    logger.info("0123: attached %d root files to the pages that embed them", attached)


def downgrade() -> None:
    op.execute("ALTER TABLE files DROP CONSTRAINT IF EXISTS files_single_parent")
    op.execute("DROP INDEX IF EXISTS idx_files_parent_page")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS parent_page_id")
