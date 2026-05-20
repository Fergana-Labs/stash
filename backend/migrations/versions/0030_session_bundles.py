"""Stashes: shareable archive of a coding session.

A stash captures the full context of an agent session: transcript,
and artifacts. Stashes are served at /b/{slug} for humans and ?format=text
for agent consumption.

Revision ID: 0030
Revises: 0029
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: prod ran an older variant of this migration when it was
    # numbered 0027 (before the merge renumbered the chain). On those DBs
    # the tables and indexes already exist, so guard every statement.
    op.execute("""
        CREATE TABLE IF NOT EXISTS stashes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            agent_name TEXT NOT NULL DEFAULT '',
            cwd TEXT,
            status TEXT NOT NULL DEFAULT 'uploading'
                CHECK (status IN ('uploading', 'summarizing', 'ready', 'failed')),
            files_touched JSONB NOT NULL DEFAULT '[]',
            transcript_storage_key TEXT,
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS stash_artifacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            stash_id UUID NOT NULL REFERENCES stashes(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            storage_key TEXT NOT NULL,
            size_bytes INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_stashes_workspace ON stashes(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stashes_session ON stashes(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stash_artifacts_stash ON stash_artifacts(stash_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stash_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS stashes CASCADE")
