"""Expose live progress for trace scoring runs."""

from alembic import op

revision = "0235"
down_revision = "0234"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE rm_scoring_runs ADD COLUMN progress jsonb")


def downgrade():
    op.execute("ALTER TABLE rm_scoring_runs DROP COLUMN progress")
