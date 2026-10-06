"""Versioned personal reward training configuration.

Revision ID: 0216
Revises: 0215
"""

from alembic import op

revision = "0216"
down_revision = "0215"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE rm_reward_models ADD COLUMN training_config jsonb")


def downgrade():
    op.execute("ALTER TABLE rm_reward_models DROP COLUMN training_config")
