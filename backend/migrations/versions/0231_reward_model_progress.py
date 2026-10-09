"""Expose live reward-model training progress."""

from alembic import op

revision = "0231"
down_revision = "0230"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE rm_reward_models ADD COLUMN progress jsonb")


def downgrade():
    op.execute("ALTER TABLE rm_reward_models DROP COLUMN progress")
