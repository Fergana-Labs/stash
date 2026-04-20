"""Add files.extracted_text + FTS index.

Stores best-effort extracted text on the file row so search and
retrieval don't have to re-open the blob.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE files ADD COLUMN IF NOT EXISTS extracted_text TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_extracted_text_fts "
        "ON files USING GIN (to_tsvector('english', coalesce(extracted_text, '')))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_files_extracted_text_fts")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS extracted_text")
