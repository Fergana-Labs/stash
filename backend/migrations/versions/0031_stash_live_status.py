"""Add 'live' status to stashes, replace 'uploading' default.

Revision ID: 0031
Revises: 0030
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Order matters: migrate data BEFORE adding the new CHECK, otherwise
    # rows with status='uploading' fail the new constraint at ADD time.
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_status_check")
    op.execute("UPDATE stashes SET status = 'live' WHERE status = 'uploading'")
    op.execute(
        "ALTER TABLE stashes ADD CONSTRAINT stashes_status_check CHECK (status IN ('live', 'summarizing', 'ready', 'failed'))"
    )
    op.execute("ALTER TABLE stashes ALTER COLUMN status SET DEFAULT 'live'")


def downgrade() -> None:
    op.execute("UPDATE stashes SET status = 'uploading' WHERE status = 'live'")
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_status_check")
    op.execute(
        "ALTER TABLE stashes ADD CONSTRAINT stashes_status_check CHECK (status IN ('uploading', 'summarizing', 'ready', 'failed'))"
    )
    op.execute("ALTER TABLE stashes ALTER COLUMN status SET DEFAULT 'uploading'")
