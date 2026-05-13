"""Rename sessions.status → sessions.summary_status with a clearer enum.

The old four values overloaded two concerns. The new enum is purely about
summarization state:

  live        -> need_summary  (uploaded, awaiting summarizer worker)
  summarizing -> need_summary  (queued by the plugin under the old flow)
  ready       -> done          (summary written)
  failed      -> failed        (gave up after MAX_ATTEMPTS)

The new 'in_progress' value is reserved for atomic claim-by-update inside
the summarizer worker — old rows never land in it directly.

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-13 00:00:00.000000
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_needs_summary")

    # Old CHECK constraint name (from migration 0036, default-named on
    # CREATE TABLE) — we drop it via the column's check_constraint.
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_status_check")

    op.execute("ALTER TABLE sessions RENAME COLUMN status TO summary_status")

    op.execute("""
        UPDATE sessions SET summary_status = CASE summary_status
            WHEN 'live'        THEN 'need_summary'
            WHEN 'summarizing' THEN 'need_summary'
            WHEN 'ready'       THEN 'done'
            ELSE summary_status
        END
        """)

    op.execute("ALTER TABLE sessions ALTER COLUMN summary_status SET DEFAULT 'need_summary'")
    op.execute(
        "ALTER TABLE sessions ADD CONSTRAINT sessions_summary_status_check "
        "CHECK (summary_status IN ('need_summary', 'in_progress', 'failed', 'done'))"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_needs_summary "
        "ON sessions (started_at) "
        "WHERE summary IS NULL AND summary_status = 'need_summary'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_needs_summary")
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_summary_status_check")
    op.execute("ALTER TABLE sessions RENAME COLUMN summary_status TO status")
    op.execute("""
        UPDATE sessions SET status = CASE status
            WHEN 'need_summary' THEN 'live'
            WHEN 'in_progress'  THEN 'summarizing'
            WHEN 'done'         THEN 'ready'
            ELSE status
        END
        """)
    op.execute("ALTER TABLE sessions ALTER COLUMN status SET DEFAULT 'live'")
    op.execute(
        "ALTER TABLE sessions ADD CONSTRAINT sessions_status_check "
        "CHECK (status IN ('live', 'summarizing', 'ready', 'failed'))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_needs_summary "
        "ON sessions (started_at) "
        "WHERE summary IS NULL AND status IN ('live', 'summarizing')"
    )
