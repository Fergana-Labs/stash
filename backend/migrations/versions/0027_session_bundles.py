"""Session bundles: shareable archive of a coding session.

A session_bundle captures the full context of an agent session: transcript,
artifacts (files touched), and an AI-generated summary. Bundles are served
at /b/{slug} for humans and ?format=text for agent consumption.

Revision ID: 0027
Revises: 0026
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE session_bundles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            agent_name TEXT NOT NULL DEFAULT '',
            cwd TEXT,
            status TEXT NOT NULL DEFAULT 'uploading'
                CHECK (status IN ('uploading', 'summarizing', 'ready', 'failed')),
            summary TEXT,
            files_touched JSONB NOT NULL DEFAULT '[]',
            transcript_storage_key TEXT,
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE bundle_artifacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bundle_id UUID NOT NULL REFERENCES session_bundles(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            storage_key TEXT NOT NULL,
            size_bytes INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_bundles_workspace ON session_bundles(workspace_id)")
    op.execute("CREATE INDEX idx_bundles_session ON session_bundles(session_id)")
    op.execute("CREATE INDEX idx_bundle_artifacts_bundle ON bundle_artifacts(bundle_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bundle_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS session_bundles CASCADE")
