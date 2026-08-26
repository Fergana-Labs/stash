"""Knowledge-map projections carry server-computed clusters.

Points gain a `cluster` index and the projection stores a named cluster list
(clustering + naming moved out of the frontend). Cached rows hold the old
point shape, so the cache is truncated — everything recomputes on next load.

Revision ID: 0205
Revises: 0204
"""

from alembic import op

revision = "0205"
down_revision = "0204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE embedding_projections ADD COLUMN clusters JSONB NOT NULL DEFAULT '[]'")
    op.execute("TRUNCATE embedding_projections")


def downgrade() -> None:
    op.execute("ALTER TABLE embedding_projections DROP COLUMN clusters")
    op.execute("TRUNCATE embedding_projections")
