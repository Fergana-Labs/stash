"""Index customer-searchable title/body without unreviewed metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0256"
down_revision = "0255"
branch_labels = None
depends_on = None

# Matches customer_wiki_search.SEARCH_VECTOR; do not import mutable app code.
SEARCH_VECTOR = (
    "setweight(to_tsvector('english', COALESCE(name, '')), 'A') || "
    "setweight(to_tsvector('english', CASE WHEN content_type = 'html' "
    "THEN regexp_replace(COALESCE(content_html, ''), '<[^>]+>', ' ', 'g') "
    "ELSE COALESCE(content_markdown, '') END), 'B')"
)


def upgrade() -> None:
    # Build without blocking page writes. Recover an invalid index left by an
    # interrupted concurrent build rather than IF NOT EXISTS silently skipping it.
    with op.get_context().autocommit_block():
        valid = op.get_bind().scalar(
            sa.text(
                "SELECT indisvalid FROM pg_index "
                "WHERE indexrelid=to_regclass('idx_pages_customer_search')"
            )
        )
        if valid is False:
            op.execute("DROP INDEX CONCURRENTLY idx_pages_customer_search")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pages_customer_search "
            f"ON pages USING GIN (({SEARCH_VECTOR})) WHERE deleted_at IS NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_pages_customer_search")
