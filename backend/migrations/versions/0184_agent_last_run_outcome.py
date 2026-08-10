"""Record how each scheduled-agent tick resolved.

Revision ID: 0184
Revises: 0183
"""

from alembic import op

revision = "0184"
down_revision = "0183"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agents ADD COLUMN last_run_outcome text
        CHECK (last_run_outcome IN (
            'started', 'ran', 'failed',
            'skipped_credits', 'skipped_no_credential', 'skipped_no_changes'
        ))
        """
    )
    op.execute("UPDATE agents SET last_run_outcome = 'failed' WHERE last_run_error IS NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN last_run_outcome")
