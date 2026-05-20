"""Drop generated session summary columns.

Revision ID: 0065
Revises: 0064
"""

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_needs_summary")
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_summary_status_check")
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_status_check")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_output_tokens")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_input_tokens")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_model")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_last_error")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_last_attempt_at")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_attempts")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_status")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE stashes DROP COLUMN IF EXISTS summary")


def downgrade() -> None:
    pass
