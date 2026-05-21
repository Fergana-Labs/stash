"""Ensure AI-generated session title cache exists.

Revision ID: 0072
Revises: 0071
"""

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS session_titles (
            workspace_id UUID NOT NULL,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, session_id),
            FOREIGN KEY (workspace_id, session_id)
                REFERENCES sessions(workspace_id, session_id)
                ON DELETE CASCADE
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_titles_updated "
        "ON session_titles(updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_titles")
