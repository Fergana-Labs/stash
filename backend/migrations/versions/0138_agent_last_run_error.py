"""Record the outcome of an agent's last scheduled run.

A curator run that dies in the worker was previously invisible: the API had
already answered 202, and the agent row carried no trace of the failure.
`last_run_error` holds the last run's error (NULL after a successful run) so
the API and CLI can surface it.

Revision ID: 0138
Revises: 0137
"""

from alembic import op

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agents ADD COLUMN last_run_error TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN last_run_error")
