"""Drop yjs_state column from notebook_pages.

Yjs/pycrdt is removed in favor of plain REST PATCH updates against
content_markdown. The column is no longer read or written.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE notebook_pages DROP COLUMN IF EXISTS yjs_state")


def downgrade() -> None:
    op.execute("ALTER TABLE notebook_pages ADD COLUMN yjs_state BYTEA")
