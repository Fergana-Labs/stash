"""Index the weighted pages search vector; drop the unusable plain one.

search_pages_fts matches against setweight(content)||setweight(keywords), but
the only FTS index on pages covered plain to_tsvector(content_markdown) — an
expression Postgres can't match to the query, so every page search was a
sequential scan that regex-stripped each page's HTML. Build the index on the
query's exact expression (PAGES_FTS_VECTOR_EXPR in files_tree_service.py —
keep the two in sync) and drop the index nothing can use.
"""

from alembic import op

revision = "0165"
down_revision = "0164"
branch_labels = None
depends_on = None

# Must stay character-for-character in sync with
# files_tree_service.PAGES_FTS_VECTOR_EXPR.
PAGES_FTS_VECTOR_EXPR = (
    "setweight(to_tsvector('english', CASE WHEN content_type = 'html' "
    "THEN regexp_replace(COALESCE(content_html, ''), '<[^>]+>', ' ', 'g') "
    "ELSE COALESCE(content_markdown, '') END), 'B') || "
    "setweight(to_tsvector('english', COALESCE(metadata->>'keywords', '')), 'A')"
)


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_fts_weighted "
        f"ON pages USING GIN (({PAGES_FTS_VECTOR_EXPR}))"
    )
    op.execute("DROP INDEX IF EXISTS idx_pages_fts")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_fts "
        "ON pages USING GIN (to_tsvector('english', content_markdown))"
    )
    op.execute("DROP INDEX IF EXISTS idx_pages_fts_weighted")
