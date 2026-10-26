"""Durable partial-input progress and a shared automatic catch-up allowance.

Revision ID: 0253
Revises: 0252
"""

from alembic import op

revision = "0253"
down_revision = "0252"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN curation_cursor jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE agents ADD COLUMN catchup_window_started timestamptz")
    op.execute("ALTER TABLE agents ADD COLUMN catchup_runs integer NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN catchup_runs")
    op.execute("ALTER TABLE agents DROP COLUMN catchup_window_started")
    op.execute("ALTER TABLE agents DROP COLUMN curation_cursor")
