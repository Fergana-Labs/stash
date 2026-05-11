"""Drop the legacy transcript blob storage.

PR 1 of the duplication cleanup collapsed agent-session storage onto
`history_events`. After running scripts/backfill_transcripts_to_events.py
on prod, the workspace-scoped `session_transcripts` table and the
share-scoped `stashes.transcript_storage_key` column carry nothing the
event rows don't already capture.

This migration drops both. The R2 blobs are intentionally NOT deleted
here — they're orphaned but readable, and a separate one-shot script
can sweep them once we're confident the row-based path is stable.

Revision ID: 0033
Revises: 0032
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_transcripts CASCADE")
    op.execute(
        "ALTER TABLE stashes DROP COLUMN IF EXISTS transcript_storage_key"
    )


def downgrade() -> None:
    # Schema-only restore. The blobs themselves are not re-linked — the
    # one-shot delete sweep runs after this migration has soaked, and
    # downgrade is a panic button, not a regular flow.
    op.execute(
        "ALTER TABLE stashes ADD COLUMN IF NOT EXISTS transcript_storage_key TEXT"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_transcripts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id VARCHAR(64) NOT NULL,
            agent_name VARCHAR(64) NOT NULL,
            storage_key TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            cwd TEXT,
            uploaded_by UUID NOT NULL REFERENCES users(id),
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, session_id)
        )
        """
    )
