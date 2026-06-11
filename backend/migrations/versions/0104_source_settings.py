"""Add per-source settings.

Revision ID: 0104
Revises: 0103
"""

from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE workspace_sources
        ADD COLUMN settings jsonb NOT NULL DEFAULT '{}'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_sources DROP COLUMN IF EXISTS settings")
