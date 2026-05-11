"""Add explicit Discover catalog curation.

Revision ID: 0034
Revises: 0033
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspaces "
        "ADD COLUMN IF NOT EXISTS discoverable BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS workspaces_public_discoverable "
        "ON workspaces (discoverable DESC, featured DESC, updated_at DESC) "
        "WHERE is_public = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS workspaces_public_discoverable")
    op.execute("ALTER TABLE workspaces DROP COLUMN IF EXISTS discoverable")
