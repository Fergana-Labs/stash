"""Re-walk X bookmark history for existing sources.

The bookmarks history walk paged at max_results=100, where X's pagination
silently drops next_token after a page or two even when thousands of
bookmarks remain — so existing sources were stamped x_bookmarks_complete
after ingesting a tiny newest-slice (one real account: 109 of 2,895). The
indexer now pages at 20, which paginates to the true end.

Clearing the completion stamp, the (100-sized) cursor, and the daily-check
stamp makes the fixed walk re-run from the top on each source's next sync.
Re-walking is idempotent per tweet (insert-or-ignore by path).
"""

from alembic import op

revision = "0179"
down_revision = "0178"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        "UPDATE user_sources SET "
        "settings = settings - 'x_bookmarks_complete' - 'x_bookmarks_cursor' "
        "- 'x_bookmarks_checked_at', "
        "updated_at = now() "
        "WHERE source_type = 'x_saves' AND settings IS NOT NULL"
    )


def downgrade() -> None:
    pass
