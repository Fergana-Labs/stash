"""Add author identity to slack_messages.

The indexer previously dropped `msg["user"]`, so no indexed Slack message was
attributable to anyone — "who said this" was unanswerable across search,
ask-the-stash, and the VFS. Rows now carry the Slack user/bot id and the
resolved display name; the transcript projection renders them inline.

Existing rows get authors on the next sync (the upsert's extra-column
freshness check sees NULL != resolved author and rewrites the row).

Revision ID: 0125
Revises: 0124
"""

from alembic import op

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE slack_messages ADD COLUMN author_id text, ADD COLUMN author text")


def downgrade() -> None:
    op.execute("ALTER TABLE slack_messages DROP COLUMN author_id, DROP COLUMN author")
