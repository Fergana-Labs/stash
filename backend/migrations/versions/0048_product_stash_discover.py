"""Add Product Stash Discover opt-in.

Revision ID: 0048
Revises: 0047
"""

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stashes ADD COLUMN IF NOT EXISTS discoverable BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stashes_discover "
        "ON stashes (discoverable DESC, updated_at DESC)"
    )


def downgrade() -> None:
    pass
