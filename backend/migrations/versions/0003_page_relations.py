"""Add page_relations table for typed knowledge graph edges.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS page_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_page_id UUID NOT NULL REFERENCES notebook_pages(id) ON DELETE CASCADE,
    relation_type VARCHAR(64) NOT NULL,
    target_page_id UUID NOT NULL REFERENCES notebook_pages(id) ON DELETE CASCADE,
    confidence REAL NOT NULL DEFAULT 0.8,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_page_id, relation_type, target_page_id)
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_page_relations_source "
        "ON page_relations(source_page_id) WHERE valid_until IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_page_relations_target "
        "ON page_relations(target_page_id) WHERE valid_until IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS page_relations")
