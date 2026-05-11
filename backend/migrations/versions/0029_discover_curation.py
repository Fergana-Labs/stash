"""Add explicit Discover catalog curation.

Revision ID: 0029
Revises: 0028
"""

from alembic import op

revision = "0029"
down_revision = "0028"
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
