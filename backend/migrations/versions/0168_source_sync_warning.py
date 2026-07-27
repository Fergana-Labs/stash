"""Add sync_warning to user_sources.

A warning is a degraded sub-feed the owner has to act on (X bookmarks need a
reconnect while posts keep syncing). It outlives the run that found it, so it
cannot live in sync_error, which every sync start clears — that made the
"reconnect X" notice visible for one sync interval a day and invisible the
rest of the time. Its own column has its own lifecycle: set when the sub-feed
fails, cleared when it succeeds.
"""

from alembic import op

revision = "0168"
down_revision = "0167"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_sources ADD COLUMN sync_warning text")


def downgrade() -> None:
    op.execute("ALTER TABLE user_sources DROP COLUMN sync_warning")
