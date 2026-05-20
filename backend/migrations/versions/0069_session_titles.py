"""Cache AI-generated session titles.

Revision ID: 0069
Revises: 0068
"""

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE session_titles (
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
    op.execute("CREATE INDEX idx_session_titles_updated ON session_titles(updated_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE session_titles")
