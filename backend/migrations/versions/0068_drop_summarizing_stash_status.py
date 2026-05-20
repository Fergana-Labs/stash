"""Drop 'summarizing' from stashes.status CHECK constraint.

The Celery summarize task was removed in #369, so no code path ever sets
`stashes.status = 'summarizing'` anymore. The status column itself is
basically vestigial — only 'live' is ever set — but we keep the column
for now and just narrow the allowed values.

Revision ID: 0068
Revises: 0067
"""

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_status_check")
    op.execute(
        "ALTER TABLE stashes ADD CONSTRAINT stashes_status_check "
        "CHECK (status IN ('live', 'ready', 'failed'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stashes DROP CONSTRAINT IF EXISTS stashes_status_check")
    op.execute(
        "ALTER TABLE stashes ADD CONSTRAINT stashes_status_check "
        "CHECK (status IN ('live', 'summarizing', 'ready', 'failed'))"
    )
