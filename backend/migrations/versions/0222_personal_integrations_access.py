"""Preserve personal integration controls for accounts present at rollout."""

from alembic import op

revision = "0222"
down_revision = "0221"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN personal_integrations_enabled boolean NOT NULL DEFAULT true"
    )
    op.execute("ALTER TABLE users ALTER COLUMN personal_integrations_enabled SET DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN personal_integrations_enabled")
