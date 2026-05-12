"""Add indexes for fast session-spine reads.

The per-stash session list now groups history_events by session_id and sorts by
last event timestamp. A focused workspace/session index keeps that query from
scanning all history rows.
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_workspace_session_created_at "
        "ON history_events (workspace_id, session_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_history_events_workspace_session_created_at")
