"""Native harness session ids for resume.

Claude Code derives its CLI session id deterministically from ours, but Codex
and opencode mint their own on turn 1 (thread_id / sessionID) and need it fed
back on every later turn. This maps our (session, harness) to that native id.

Revision ID: 0123
Revises: 0122
"""

from alembic import op

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE harness_sessions (
            session_id text NOT NULL,
            harness    text NOT NULL,
            native_id  text NOT NULL,
            PRIMARY KEY (session_id, harness)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS harness_sessions")
