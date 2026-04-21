"""Add content_hash + embed_stale to embedded tables.

`notebook_pages` already has `content_hash` (used for optimistic
concurrency); we just add `embed_stale` there. `table_rows` and
`history_events` get both columns so we can gate re-embed on content
change and let a reconciler retry failed fire-and-forget embeds.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE notebook_pages ADD COLUMN IF NOT EXISTS embed_stale BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE table_rows ADD COLUMN IF NOT EXISTS content_hash TEXT")
    op.execute("ALTER TABLE table_rows ADD COLUMN IF NOT EXISTS embed_stale BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE history_events ADD COLUMN IF NOT EXISTS content_hash TEXT")
    op.execute("ALTER TABLE history_events ADD COLUMN IF NOT EXISTS embed_stale BOOLEAN NOT NULL DEFAULT FALSE")

    # Partial indexes for the reconciler: find rows that need re-embedding.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notebook_pages_embed_stale "
        "ON notebook_pages(id) WHERE embed_stale"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_table_rows_embed_stale "
        "ON table_rows(id) WHERE embed_stale"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_embed_stale "
        "ON history_events(id) WHERE embed_stale"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_history_events_embed_stale")
    op.execute("DROP INDEX IF EXISTS idx_table_rows_embed_stale")
    op.execute("DROP INDEX IF EXISTS idx_notebook_pages_embed_stale")
    op.execute("ALTER TABLE history_events DROP COLUMN IF EXISTS embed_stale")
    op.execute("ALTER TABLE history_events DROP COLUMN IF EXISTS content_hash")
    op.execute("ALTER TABLE table_rows DROP COLUMN IF EXISTS embed_stale")
    op.execute("ALTER TABLE table_rows DROP COLUMN IF EXISTS content_hash")
    op.execute("ALTER TABLE notebook_pages DROP COLUMN IF EXISTS embed_stale")
