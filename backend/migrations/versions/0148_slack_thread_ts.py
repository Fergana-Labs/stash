"""Add thread linkage to slack_messages.

Thread replies were either never fetched (backfill) or stored with their
`thread_ts` discarded (live ingest), so replies rendered as free-floating
top-level lines and most of them were simply missing. Rows now record the
parent's ts; NULL means a top-level message.

Existing rows get thread_ts on the next sync (the upsert's extra-column
freshness check sees NULL != parent ts and rewrites the row).

Revision ID: 0148
Revises: 0147
"""

from alembic import op

revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE slack_messages ADD COLUMN thread_ts text")


def downgrade() -> None:
    op.execute("ALTER TABLE slack_messages DROP COLUMN thread_ts")
