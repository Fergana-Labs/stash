"""Rename agent_name → tag_name in history_events and session_transcripts.

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE history_events RENAME COLUMN agent_name TO tag_name")
    op.execute("ALTER TABLE session_transcripts RENAME COLUMN agent_name TO tag_name")
    op.execute("ALTER INDEX IF EXISTS idx_history_events_agent_session RENAME TO idx_history_events_tag_session")


def downgrade() -> None:
    op.execute("ALTER TABLE history_events RENAME COLUMN tag_name TO agent_name")
    op.execute("ALTER TABLE session_transcripts RENAME COLUMN tag_name TO agent_name")
    op.execute("ALTER INDEX IF EXISTS idx_history_events_tag_session RENAME TO idx_history_events_agent_session")
