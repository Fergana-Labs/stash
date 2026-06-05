"""Make Notion full-text searchable.

notion_index was index-only (no body stored). Notion's crawl already renders
each page's blocks to markdown to discover sub-pages, so we now store that text
and treat notion_index as a copied-content table — adding the content/embedding
columns + the FTS index the other content tables have (migration 0084). Existing
rows get NULL content until the next sync re-populates them.

Revision ID: 0090
Revises: 0089
"""

from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE notion_index
            ADD COLUMN content      text,
            ADD COLUMN content_hash text,
            ADD COLUMN embedding    vector(384),
            ADD COLUMN embed_stale  boolean NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        "CREATE INDEX notion_index_fts_idx ON notion_index "
        "USING gin (to_tsvector('english', coalesce(content, '')))"
    )
    op.execute("CREATE INDEX notion_index_embed_stale_idx ON notion_index (id) WHERE embed_stale")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS notion_index_embed_stale_idx")
    op.execute("DROP INDEX IF EXISTS notion_index_fts_idx")
    op.execute(
        "ALTER TABLE notion_index "
        "DROP COLUMN content, DROP COLUMN content_hash, "
        "DROP COLUMN embedding, DROP COLUMN embed_stale"
    )
