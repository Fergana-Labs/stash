"""Persist training evidence and private model artifacts.

Revision ID: 0211
Revises: 0210
"""

from alembic import op

revision = "0211"
down_revision = "0210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE rm_reward_models ADD COLUMN training_pairs jsonb NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE rm_reward_models ADD COLUMN artifact_key text")


def downgrade() -> None:
    op.execute("ALTER TABLE rm_reward_models DROP COLUMN artifact_key, DROP COLUMN training_pairs")
