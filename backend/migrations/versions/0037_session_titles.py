"""Cache AI-generated session titles.

Revision ID: 0037
Revises: 0036
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE session_titles (
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, session_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE session_titles")
