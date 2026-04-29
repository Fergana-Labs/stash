"""Add unique constraint on session_transcripts(workspace_id, session_id).

Prevents duplicate imports of the same conversation.

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_transcripts_ws_session")
    op.execute(
        "CREATE UNIQUE INDEX idx_transcripts_ws_session "
        "ON session_transcripts(workspace_id, session_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_transcripts_ws_session")
    op.execute(
        "CREATE INDEX idx_transcripts_ws_session "
        "ON session_transcripts(workspace_id, session_id)"
    )
