"""Add per-source settings.

Revision ID: 0103
Revises: 0102
"""

from alembic import op

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE workspace_sources
        ADD COLUMN settings jsonb NOT NULL DEFAULT '{}'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_sources DROP COLUMN IF EXISTS settings")
