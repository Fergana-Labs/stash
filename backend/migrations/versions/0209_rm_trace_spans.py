"""Preserve timed operations and parent relationships on reward-model traces."""

from alembic import op

revision = "0209"
down_revision = "0208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE rm_traces ADD COLUMN spans jsonb NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE rm_traces DROP COLUMN spans")
