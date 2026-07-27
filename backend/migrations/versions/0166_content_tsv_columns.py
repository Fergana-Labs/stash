"""Store each content document's tsvector instead of re-parsing it per query.

search_documents ranked hits with ts_rank(to_tsvector(content), query), which
re-parses every matching document's full text on every search — seconds per
query for a user with a large corpus. A stored generated column computes the
same expression once at write time, so matching and ranking read the
pre-built vector. The GIN index moves to the stored column (same lexemes, so
identical matches and ranks) and the old expression index is dropped.
"""

from alembic import op

revision = "0166"
down_revision = "0165"
branch_labels = None
depends_on = None

CONTENT_TABLES = [
    "github_documents",
    "slack_messages",
    "granola_notes",
    "gong_documents",
    "notion_index",
    "drive_documents",
    "instagram_save_docs",
    "x_save_docs",
]


def upgrade() -> None:
    for table in CONTENT_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN content_tsv tsvector "
            f"GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED"
        )
        op.execute(f"CREATE INDEX {table}_tsv_idx ON {table} USING gin (content_tsv)")
        op.execute(f"DROP INDEX {table}_fts_idx")
        op.execute(f"ANALYZE {table}")


def downgrade() -> None:
    for table in CONTENT_TABLES:
        op.execute(
            f"CREATE INDEX {table}_fts_idx ON {table} "
            f"USING gin (to_tsvector('english', coalesce(content, '')))"
        )
        op.execute(f"DROP INDEX {table}_tsv_idx")
        op.execute(f"ALTER TABLE {table} DROP COLUMN content_tsv")
