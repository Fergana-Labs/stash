"""Stash handoff curator + server-side summarizer state.

- New table `stash_handoffs`: per-workspace curated orientation doc with
  pin/edit metadata.
- New columns on `sessions` for the summarizer worker (attempts, model used,
  token counts).
- Backfill: any session with NULL summary that's still in the 'live' state
  flips to 'summarizing' so the new worker picks it up.

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-12 00:00:00.000000
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS stash_handoffs (
            workspace_id UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
            body_markdown TEXT NOT NULL DEFAULT '',
            input_fingerprint TEXT,
            model VARCHAR(64),
            input_tokens INT,
            output_tokens INT,
            turns_used INT,
            tool_calls_used INT,
            generated_at TIMESTAMPTZ,
            stale BOOLEAN NOT NULL DEFAULT TRUE,
            stale_marked_at TIMESTAMPTZ DEFAULT now(),
            last_attempt_at TIMESTAMPTZ,
            last_error TEXT,
            consecutive_failures INT NOT NULL DEFAULT 0,
            pinned_at TIMESTAMPTZ,
            pinned_by UUID REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stash_handoffs_stale "
        "ON stash_handoffs (stale_marked_at) "
        "WHERE stale = TRUE AND pinned_at IS NULL"
    )

    op.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_attempts INT NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_last_attempt_at TIMESTAMPTZ"
    )
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_last_error TEXT")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_model VARCHAR(64)")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_input_tokens INT")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary_output_tokens INT")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_needs_summary "
        "ON sessions (started_at) "
        "WHERE summary IS NULL AND status IN ('live', 'summarizing')"
    )

    # Backfill: any existing summary-less session in 'live' status moves to
    # 'summarizing' so the new worker picks them up on first tick. Sessions
    # already in 'summarizing' (plugin set them on its way to a now-deleted
    # LLM call) are also already eligible. 'failed' and 'ready' are untouched.
    op.execute(
        "UPDATE sessions SET status = 'summarizing' "
        "WHERE summary IS NULL AND status = 'live'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_needs_summary")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_output_tokens")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_input_tokens")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_model")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_last_error")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_last_attempt_at")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS summary_attempts")
    op.execute("DROP INDEX IF EXISTS idx_stash_handoffs_stale")
    op.execute("DROP TABLE IF EXISTS stash_handoffs")
