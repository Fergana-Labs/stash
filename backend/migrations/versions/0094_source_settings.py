"""Add per-source settings.

Revision ID: 0094
Revises: 0093
"""

from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE workspace_sources
        ADD COLUMN settings jsonb NOT NULL DEFAULT '{}'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_sources DROP COLUMN IF EXISTS settings")
