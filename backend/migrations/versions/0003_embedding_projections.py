"""Add embedding_projections cache table for dashboard visualizations.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-13
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS embedding_projections (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL DEFAULT '_all',
    points JSONB NOT NULL DEFAULT '[]',
    embedding_count INTEGER NOT NULL DEFAULT 0,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, source_type)
)
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS embedding_projections")
