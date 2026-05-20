"""Add persisted Yjs state for collaborative page editing.

Revision ID: 0064
Revises: 0063
"""

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS page_collab_documents (
            page_id UUID PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            yjs_state BYTEA NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_page_collab_documents_workspace "
        "ON page_collab_documents(workspace_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_page_collab_documents_workspace")
    op.execute("DROP TABLE IF EXISTS page_collab_documents")
