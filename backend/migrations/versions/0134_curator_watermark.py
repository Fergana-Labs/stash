"""Split the curator's delta watermark from the cron baseline.

`last_run_at` doubled as both the schedule baseline and the curator's
curated-up-to watermark, so a skipped or failed run had to choose between
re-firing every beat and permanently discarding the un-curated delta.
`curated_through` is the watermark; `last_run_at` is only the cron baseline.

Revision ID: 0134
Revises: 0133
"""

from alembic import op

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN curated_through timestamptz")
    op.execute("UPDATE agents SET curated_through = last_run_at WHERE is_curator")


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS curated_through")
