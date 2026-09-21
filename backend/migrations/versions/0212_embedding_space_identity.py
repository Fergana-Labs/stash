"""Version stored embeddings and projection caches.

Revision ID: 0212
Revises: 0211
"""

from alembic import op
from sqlalchemy import text

from backend.services.embeddings import space_id

revision = "0212"
down_revision = "0211"
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

    # This release changes bookkeeping, not the embedding provider. Deploy
    # with the existing model configuration so its vectors keep their identity.
    op.get_bind().execute(
        text("INSERT INTO embedding_space_state (singleton, space_id) VALUES (TRUE, :space)"),
        {"space": space_id()},
    )


def downgrade() -> None:
    op.execute("TRUNCATE embedding_projections")
    op.execute("ALTER TABLE embedding_projections DROP COLUMN embedding_space")
    op.execute("DROP TABLE embedding_space_state")
