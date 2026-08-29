"""Version stored embeddings and projection caches.

Revision ID: 0207
Revises: 0206
"""

from alembic import op

revision = "0207"
down_revision = "0206"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE embedding_space_state ("
        "singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton), "
        "space_id TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
    )
    op.execute("ALTER TABLE embedding_projections ADD COLUMN embedding_space TEXT")
    op.execute("TRUNCATE embedding_projections")

    tables = [
        "pages",
        "table_rows",
        "history_events",
        "files",
        "granola_notes",
        "notion_index",
        "instagram_save_docs",
        "x_save_docs",
        "drive_documents",
        "slack_messages",
        "gong_documents",
        "github_documents",
    ]
    for table in tables:
        op.execute(
            f"UPDATE {table} SET embedding = NULL, embed_stale = TRUE WHERE embedding IS NOT NULL"
        )


def downgrade() -> None:
    op.execute("TRUNCATE embedding_projections")
    op.execute("ALTER TABLE embedding_projections DROP COLUMN embedding_space")
    op.execute("DROP TABLE embedding_space_state")
