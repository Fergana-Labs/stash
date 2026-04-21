"""Add knowledge_density_cache for precomputed topic clusters.

The knowledge-density viz runs full-text stemming over every accessible
notebook page, table row, and history event. On users with real content
volume this takes minutes — long enough that HTTP timeouts fire and the
UI renders blank. Mirror the `embedding_projections` pattern: precompute
into a DB-backed cache so the endpoint becomes a pure read.

Revision ID: 0017
Revises: 0016
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS knowledge_density_cache (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    clusters JSONB NOT NULL DEFAULT '[]',
    source_signature BIGINT NOT NULL DEFAULT 0,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_knowledge_density_cache_computed_at "
        "ON knowledge_density_cache(computed_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_knowledge_density_cache_computed_at")
    op.execute("DROP TABLE IF EXISTS knowledge_density_cache CASCADE")
