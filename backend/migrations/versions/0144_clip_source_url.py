"""Record where a clipped file came from.

Web clips are ordinary pages/files in the Clips folder. Pages carry the
source URL in their metadata jsonb, but files have no metadata column, so
clipped binaries (PDFs) get a dedicated column.

Revision ID: 0144
Revises: 0143
"""

from alembic import op

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE files ADD COLUMN source_url text")


def downgrade() -> None:
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS source_url")
