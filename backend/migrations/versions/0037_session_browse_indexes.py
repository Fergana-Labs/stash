"""Add session browse indexes.

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-11 19:20:00.000000
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_events_workspace_session_created "
        "ON history_events(workspace_id, session_id, created_at) "
        "WHERE session_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_history_events_workspace_session_created")
