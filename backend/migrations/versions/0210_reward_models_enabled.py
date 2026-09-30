"""Enable reward models only for accounts created after this rollout.

Revision ID: 0210
Revises: 0209
"""

from alembic import op

revision = "0210"
down_revision = "0209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN reward_models_enabled boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE users ALTER COLUMN reward_models_enabled SET DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN reward_models_enabled")
